"""OAuth login façade: runs the PKCE loopback flow, persists each login as a named
`cloudinary://` entry in `config.json`, and refreshes tokens when a saved login is selected."""
import secrets
import webbrowser

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
from cloudinary_cli.utils.utils import log_exception


def login(region=None, name=None, set_default=False):
    """
    Run the interactive browser login and persist the resulting session as a named config entry.

    Returns the saved config name, or None on failure.
    """
    if name and is_reserved_config_name(name):
        raise RuntimeError(f"'{name}' is a reserved configuration name.")
    region = normalize_region(region or CLOUDINARY_REGION)
    session = _run_browser_flow(region)
    if not session.cloud_name:
        raise RuntimeError("Login token did not include a cloud name; cannot save this login.")
    config_name = name or _derive_config_name(session.cloud_name, region)
    update_config({config_name: to_cloudinary_url(session)})

    if set_default or _should_auto_default(config_name):
        set_default_config(config_name)
    return config_name


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
    """Remove a saved OAuth login by name. Returns "removed", "not_found", or "not_oauth"."""
    saved = load_config()
    if name not in saved:
        return "not_found"
    if not is_oauth_url(saved[name]):
        return "not_oauth"
    remove_config_keys(name)
    return "removed"


def refresh_url_if_stale(name, url, force=False):
    """
    Given a saved config value, refresh it if it is a stale OAuth login (rewriting the stored
    URL on token rotation). Non-OAuth and still-fresh URLs are returned unchanged. With force=True
    a still-fresh token is refreshed too (used by the explicit `config --refresh --force`).

    The refresh consumes a single-use refresh token, so the whole read-refresh-write runs under
    a cross-process lock with the freshness re-checked inside it: a peer that refreshed while we
    waited leaves a fresh token we adopt instead of refreshing (and burning) it again.
    """
    if not is_oauth_url(url):
        return url

    session = from_cloudinary_url(url)
    if (session.is_fresh() and not force) or not session.refresh_token:
        return url

    with config_lock():
        url = load_config().get(name, url)  # re-read: a peer may have refreshed while we waited
        session = from_cloudinary_url(url)
        if (session.is_fresh() and not force) or not session.refresh_token:
            return url

        try:
            token_response = flow.refresh(session.refresh_token, session.region)
        except requests.RequestException as e:
            log_exception(e, debug_message="OAuth token refresh failed")
            return url

        # Hydra rotates refresh tokens; keep the old one only if a new one was not returned.
        token_response.setdefault("refresh_token", session.refresh_token)
        refreshed_url = to_cloudinary_url(session.updated_from(token_response))
        update_config({name: refreshed_url})
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
    if not webbrowser.open(authorize_url):
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
