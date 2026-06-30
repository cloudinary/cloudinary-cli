"""OAuth 2.0 Authorization Code + PKCE protocol helpers (RFC 8252): build the authorize URL,
exchange a code, refresh a token. Pure protocol, no file I/O or global state."""
import base64
import hashlib
import secrets
import urllib.parse

import requests

from cloudinary_cli.defaults import (
    oauth_authorize_url_for_region,
    oauth_token_url_for_region,
    oauth_revoke_url_for_region,
    OAUTH_CLIENT_ID,
    OAUTH_SCOPES,
    OAUTH_HTTP_TIMEOUT_SECONDS,
)


def generate_pkce_pair():
    """Return (code_verifier, code_challenge) for the S256 PKCE method."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(challenge, state, redirect_uri, region):
    query = urllib.parse.urlencode({
        "client_id": OAUTH_CLIENT_ID,
        "response_type": "code",
        "scope": OAUTH_SCOPES,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{oauth_authorize_url_for_region(region)}?{query}"


def exchange_code(auth_code, verifier, redirect_uri, region):
    """Exchange the authorization code for tokens. Public PKCE client - no client_secret."""
    resp = requests.post(oauth_token_url_for_region(region), data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": OAUTH_CLIENT_ID,
        "code_verifier": verifier,
    }, timeout=OAUTH_HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def refresh(refresh_token, region):
    resp = requests.post(oauth_token_url_for_region(region), data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": OAUTH_CLIENT_ID,
    }, timeout=OAUTH_HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


_MAX_OAUTH_DESCRIPTION = 80


def oauth_error_body(exc):
    """The raw response body text from a failed token request, or None if no response is attached.
    Logged verbatim at debug for investigation - it carries the full server error_description."""
    resp = getattr(exc, "response", None)
    return resp.text if resp is not None else None


def oauth_error_detail(exc):
    """The server's OAuth error code from a failed token request (RFC 6749 §5.2), or None when the
    response carries no parseable OAuth error body. The error_description is appended only when it is
    short; the endpoint often returns a multi-sentence boilerplate paragraph that is noise in a log."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    error = body.get("error")
    if not error:
        return None
    description = body.get("error_description")
    if description and len(description) <= _MAX_OAUTH_DESCRIPTION:
        return f"{error}: {description}"
    return error


def revoke(token, region, token_type_hint="refresh_token"):
    """Revoke a token at the authorization server (RFC 7009). Revoking the refresh token ends the
    offline-access grant so it can no longer mint new access tokens."""
    resp = requests.post(oauth_revoke_url_for_region(region), data={
        "token": token,
        "token_type_hint": token_type_hint,
        "client_id": OAUTH_CLIENT_ID,
    }, timeout=OAUTH_HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
