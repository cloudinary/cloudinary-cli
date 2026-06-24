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
from cloudinary_cli.utils.config_utils import load_config, update_config, remove_config_keys, config_lock
from cloudinary_cli.utils.utils import log_exception


def login(region=None, name=None):
    """
    Run the interactive browser login and persist the resulting session as a named config entry.

    Returns the saved config name, or None on failure.
    """
    region = normalize_region(region or CLOUDINARY_REGION)
    session = _run_browser_flow(region)
    if not session.cloud_name:
        raise RuntimeError("Login token did not include a cloud name; cannot save this login.")
    config_name = name or _derive_config_name(session.cloud_name, region)
    update_config({config_name: to_cloudinary_url(session)})
    return config_name


def logout(name):
    """Remove a saved OAuth login by name. Returns "removed", "not_found", or "not_oauth"."""
    saved = load_config()
    if name not in saved:
        return "not_found"
    if not is_oauth_url(saved[name]):
        return "not_oauth"
    remove_config_keys(name)
    return "removed"


def refresh_url_if_stale(name, url):
    """
    Given a saved config value, refresh it if it is a stale OAuth login (rewriting the stored
    URL on token rotation). Non-OAuth and still-fresh URLs are returned unchanged.

    The refresh consumes a single-use refresh token, so the whole read-refresh-write runs under
    a cross-process lock with the freshness re-checked inside it: a peer that refreshed while we
    waited leaves a fresh token we adopt instead of refreshing (and burning) it again.
    """
    if not is_oauth_url(url):
        return url

    session = from_cloudinary_url(url)
    if session.is_fresh() or not session.refresh_token:
        return url

    with config_lock():
        url = load_config().get(name, url)  # re-read: a peer may have refreshed while we waited
        session = from_cloudinary_url(url)
        if session.is_fresh() or not session.refresh_token:
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


def find_sole_oauth_login():
    """Return (name, url) of the only saved OAuth login, or None if there are zero or many."""
    oauth_logins = [(name, url) for name, url in load_config().items() if is_oauth_url(url)]
    return oauth_logins[0] if len(oauth_logins) == 1 else None


def list_oauth_login_names():
    """Return the names of all saved OAuth logins."""
    return [name for name, url in load_config().items() if is_oauth_url(url)]


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
