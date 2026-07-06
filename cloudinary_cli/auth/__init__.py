"""OAuth login façade: runs the PKCE loopback flow and persists each login as a named
`cloudinary://` entry in `config.json`. Token refresh lives in `auth.refresh`, re-exported here."""
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
from cloudinary_cli.auth.refresh import (
    refresh_url_if_stale,
    refresh_config,
    refresh_configs,
    relogin_command,
    list_oauth_login_names,
)
from cloudinary_cli.defaults import logger, normalize_region, DEFAULT_REGION, CLOUDINARY_REGION
from cloudinary_cli.utils.config_utils import (
    load_config,
    remove_config_keys,
    save_named_config,
    is_reserved_config_name,
)
from cloudinary_cli.utils.utils import log_exception, is_interactive

__all__ = [
    "login",
    "logout",
    "refresh_url_if_stale",
    "refresh_config",
    "refresh_configs",
    "relogin_command",
    "list_oauth_login_names",
]


def login(region=None, name=None, set_default=False):
    """
    Run the interactive browser login and persist the resulting session as a named config entry.

    Returns (config_name, default_status), where default_status is:
      "made"    - this login just became the default (explicit --set-default, or auto-defaulted as
                  the sole login),
      "already" - the re-logged-into config was already the stored default,
      "no"      - it is not the default.
    """
    if name and is_reserved_config_name(name):
        raise RuntimeError(f"'{name}' is a reserved configuration name.")
    region = normalize_region(region or CLOUDINARY_REGION)
    session = _run_browser_flow(region)
    if not session.cloud_name:
        raise RuntimeError("Login token did not include a cloud name; cannot save this login.")
    config_name = name or _derive_config_name(session.cloud_name, region)

    default_status = save_named_config(config_name, to_cloudinary_url(session), set_default=set_default)
    return config_name, default_status


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
