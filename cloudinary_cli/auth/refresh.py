"""Non-interactive OAuth token refresh: rotates saved tokens on read/401 under a cross-process lock."""
import requests

from cloudinary_cli.auth import flow
from cloudinary_cli.auth.session import from_cloudinary_url, to_cloudinary_url, is_oauth_url
from cloudinary_cli.defaults import logger, DEFAULT_REGION
from cloudinary_cli.utils.config_utils import (
    load_config,
    update_config,
    config_lock,
    user_config_names,
)
from cloudinary_cli.utils.utils import token_hint, expiry_hint

# Configs already warned about a failed refresh, so a bulk run warns once per config, not per asset.
_refresh_warned = set()


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
            body = flow.oauth_error_body(e)
            logger.debug(f"OAuth token refresh failed for '{name}': {e}"
                         + (f"; response body: {body}" if body else ""), exc_info=True)
            if name not in _refresh_warned:
                _refresh_warned.add(name)
                detail = flow.oauth_error_detail(e)
                reason = f" ({detail})" if detail else ""
                logger.warning(f"Could not refresh the OAuth token for '{name}'{reason}; using the "
                               f"existing token, which may be expired. Re-login with "
                               f"`{relogin_command(name)}`.")
            return url

        _refresh_warned.discard(name)

        # Refresh tokens rotate; keep the old one only if a new one was not returned.
        token_response.setdefault("refresh_token", session.refresh_token)
        refreshed = session.updated_from(token_response)
        refreshed_url = to_cloudinary_url(refreshed)
        update_config({name: refreshed_url})
        logger.debug(f"Refreshed OAuth token for '{name}': "
                     f"access {token_hint(session.access_token)} -> {token_hint(refreshed.access_token)}, "
                     f"refresh {token_hint(session.refresh_token)} -> {token_hint(refreshed.refresh_token)}, "
                     f"expires {expiry_hint(session.expires_at)} -> {expiry_hint(refreshed.expires_at)}")
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
