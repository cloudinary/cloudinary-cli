"""OAuth login façade: runs the PKCE loopback flow, persists each login as a named
`cloudinary://` entry in `config.json`, and refreshes tokens when a saved login is selected."""
import secrets
import webbrowser
from datetime import datetime, timezone

import requests

from cloudinary_cli.auth import flow
from cloudinary_cli.auth.loopback_server import start_callback_server, wait_for_callback
from cloudinary_cli.auth.session import (
    Session,
    to_cloudinary_url,
    from_cloudinary_url,
    is_oauth_url,
)
from cloudinary_cli.defaults import logger, normalize_region, DEFAULT_REGION, CLOUDINARY_REGION
from cloudinary_cli.utils.config_utils import (
    load_config,
    update_config,
    remove_config_keys,
    config_lock,
    user_config_names,
    get_default_config_name,
    set_default_config,
    is_reserved_config_name,
    is_env_configured,
)
from cloudinary_cli.utils.utils import log_exception, is_interactive

# Configs already warned about a failed refresh, so a bulk run warns once per config, not per asset.
_refresh_warned = set()


def _token_hint(token):
    """Non-sensitive token fingerprint (trailing chars + length) for debug logs."""
    if not token:
        return "<none>"
    return f"…{token[-6:]}({len(token)} chars)"


def _expiry_hint(epoch):
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError):
        return str(epoch)


def login(region=None, name=None, set_default=False):
    """
    Run the interactive browser login and persist the resulting session as a named config entry.

    Returns (config_name, is_default), where is_default is True when this login was made the default
    configuration (explicitly with set_default, or automatically as the sole login).
    """
    if name and is_reserved_config_name(name):
        raise RuntimeError(f"'{name}' is a reserved configuration name.")
    region = normalize_region(region or CLOUDINARY_REGION)
    session = _run_browser_flow(region)
    if not session.cloud_name:
        raise RuntimeError("Login token did not include a cloud name; cannot save this login.")
    config_name = name or _derive_config_name(session.cloud_name, region)
    update_config({config_name: to_cloudinary_url(session)})

    is_default = bool(set_default or _should_auto_default(config_name))
    if is_default:
        set_default_config(config_name)
    return config_name, is_default


def _should_auto_default(name):
    """
    True when the just-saved login should become the default without an explicit flag: it is the
    only saved config, the environment configures nothing, and no default is already stored.

    A stored default outranks the environment, so auto-defaulting is suppressed when an env config
    is present: a single `cld login` must not silently override a user's CLOUDINARY_URL. They can
    still opt in with `--set-default`.
    """
    cfg = load_config()
    return (
        user_config_names(cfg) == [name]
        and not is_env_configured()
        and not get_default_config_name()
    )


def logout(name):
    """
    Log out of a saved OAuth login by name: revoke its refresh token at the authorization server,
    then remove the saved configuration. The local entry is always removed even if revocation fails
    (offline, server error), so logout never leaves a stale entry behind.

    Returns "removed" (revoked and removed), "revoke_failed" (removed locally but the token could not
    be revoked), "not_found", or "not_oauth".
    """
    saved = load_config()
    if name not in saved:
        return "not_found"
    if not is_oauth_url(saved[name]):
        return "not_oauth"

    revoked = _revoke_login(name, saved[name])
    remove_config_keys(name)
    return "removed" if revoked else "revoke_failed"


def _revoke_login(name, url):
    """Best-effort revocation of a saved login's refresh token. Returns True on success (or when
    there is nothing to revoke), False if the revoke request failed."""
    session = from_cloudinary_url(url)
    if not session.refresh_token:
        return True
    try:
        flow.revoke(session.refresh_token, session.region)
        return True
    except requests.RequestException as e:
        log_exception(e, debug_message=f"Could not revoke the OAuth token for '{name}'")
        return False


def _should_refresh(session, expected, force):
    """Whether `session` should be rotated. `force` rotates any refreshable token; `expected` rotates
    only while disk still holds that exact token (else a peer rotated -> adopt); otherwise rotate when
    clock-stale."""
    if not session.refresh_token:
        return False
    if force:
        return True
    if expected is not None:
        return session.access_token == expected
    return not session.is_fresh()


def refresh_url_if_stale(name, url, force=False, expected=None):
    """
    Refresh a saved config value if its OAuth token should rotate, rewriting the stored URL; other
    URLs are returned unchanged. The single-use refresh runs under a cross-process lock, re-checking
    the freshly re-read disk token so a peer's rotation is adopted instead of burning another refresh.
    """
    if not is_oauth_url(url):
        return url

    if not _should_refresh(from_cloudinary_url(url), expected, force):
        return url

    with config_lock():
        url = load_config().get(name, url)  # re-read: a peer may have rotated while we waited
        session = from_cloudinary_url(url)
        if not _should_refresh(session, expected, force):
            return url

        try:
            token_response = flow.refresh(session.refresh_token, session.region)
        except requests.RequestException as e:
            # Serve the stale token but surface the failure once per config.
            log_exception(e, debug_message="OAuth token refresh failed")
            if name not in _refresh_warned:
                _refresh_warned.add(name)
                logger.warning(f"Could not refresh the OAuth token for '{name}'; using the existing "
                               f"token, which may be expired. Re-login with `{relogin_command(name)}`.")
            return url

        _refresh_warned.discard(name)

        # Refresh tokens rotate; keep the old one only if a new one was not returned.
        token_response.setdefault("refresh_token", session.refresh_token)
        refreshed = session.updated_from(token_response)
        refreshed_url = to_cloudinary_url(refreshed)
        update_config({name: refreshed_url})
        logger.debug(f"Refreshed OAuth token for '{name}': "
                     f"access {_token_hint(session.access_token)} -> {_token_hint(refreshed.access_token)}, "
                     f"refresh {_token_hint(session.refresh_token)} -> {_token_hint(refreshed.refresh_token)}, "
                     f"expires {_expiry_hint(session.expires_at)} -> {_expiry_hint(refreshed.expires_at)}")
        return refreshed_url


def refresh_config(name, force=False):
    """
    Refresh a single saved OAuth config by name and report the outcome. Returns one of:
      "not_found", "not_oauth", "fresh" (skipped, still valid), "refreshed", or "failed"
    ("failed" = stale/forced but no refresh token, or the network refresh did not rotate it).
    """
    cfg = load_config()
    if name not in user_config_names(cfg):
        return "not_found"
    url = cfg[name]
    if not is_oauth_url(url):
        return "not_oauth"

    session = from_cloudinary_url(url)
    if session.is_fresh() and not force:
        return "fresh"
    if not session.refresh_token:
        return "failed"

    new_url = refresh_url_if_stale(name, url, force=force)
    return "refreshed" if new_url != url else "failed"


def refresh_configs(force=False):
    """Refresh every saved OAuth config. Returns {name: outcome} (see refresh_config)."""
    return {name: refresh_config(name, force=force) for name in list_oauth_login_names()}


def relogin_command(name):
    """
    Build the `cld login` command to re-authenticate a saved OAuth config, preserving its region
    (a non-default region must be passed explicitly so the right OAuth host is used).
    """
    cmd = f"cld login {name}"
    url = load_config().get(name)
    region = from_cloudinary_url(url).region if url and is_oauth_url(url) else None
    if region and region != DEFAULT_REGION:
        cmd += f" --region {region}"
    return cmd


def list_oauth_login_names():
    """Return the names of all saved OAuth logins."""
    cfg = load_config()
    return [name for name in user_config_names(cfg) if is_oauth_url(cfg[name])]


def _run_browser_flow(region):
    verifier, challenge = flow.generate_pkce_pair()
    state = secrets.token_urlsafe(16)
    httpd, redirect_uri = start_callback_server()

    authorize_url = flow.build_authorize_url(challenge, state, redirect_uri, region)
    logger.info("Opening browser to log in to Cloudinary...")
    opened = webbrowser.open(authorize_url)
    if not opened and not is_interactive():
        # No browser and no interactive terminal: nobody can complete the redirect, so fail fast
        # instead of blocking until the callback times out. Headless runs use a pre-set config.
        httpd.server_close()
        raise RuntimeError(
            "cld login needs an interactive browser session, but no browser could be opened and "
            "this is not an interactive terminal. For headless/CI use, configure credentials with "
            "an API-key URL instead: `cld -c cloudinary://<key>:<secret>@<cloud> <command>` or save "
            "one with `cld config -n <name> <url>` and select it via `-C <name>`."
        )
    if not opened:
        logger.info(f"Could not open a browser. Visit this URL to log in:\n{authorize_url}")
    else:
        logger.info(f"If it doesn't open automatically, visit:\n{authorize_url}")

    auth_code, returned_state = wait_for_callback(httpd)
    if returned_state != state:
        raise RuntimeError("State mismatch - possible CSRF, aborting.")

    token_response = flow.exchange_code(auth_code, verifier, redirect_uri, region)
    return Session.from_token_response(token_response, region=region)


def _derive_config_name(cloud_name, region):
    """
    Build the saved name: cloud_name + region geo suffix (when not default) + auth-type suffix
    only when the base name collides with a DIFFERENT auth type (re-login overwrites in place).
    """
    base = cloud_name
    if region != DEFAULT_REGION:
        base = f"{base}-{region[len('api-'):]}"  # api-eu -> "<cloud>-eu"

    config = load_config()
    existing = config.get(base)
    if existing is None or is_oauth_url(existing):
        return base  # free, or same (oauth) type -> overwrite in place
    return f"{base}-oauth"  # taken by an api-key config -> suffix the new oauth entry
