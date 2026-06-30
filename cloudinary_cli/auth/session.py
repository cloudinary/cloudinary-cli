"""The OAuth session and its `cloudinary://` URL codec. A login is persisted as a `cloudinary://`
URL so it flows through the SDK parser and existing config machinery unchanged; the `Session`
dataclass is the in-memory form, `to_cloudinary_url`/`from_cloudinary_url` the persisted one."""
import base64
import json
import time
import urllib.parse
from dataclasses import dataclass

from cloudinary_cli.defaults import (
    OAUTH_EXPIRY_SKEW_SECONDS,
    api_host_for_region,
)

# Query-string keys that carry the OAuth session inside a cloudinary:// URL.
_OAUTH_MARKER = "oauth_token"

_OAUTH_INTERNAL_KEYS = frozenset({"refresh_token", "issued_at", "expires_at", "region", "issuer"})


def strip_oauth_internal_keys(config_dict):
    return {k: v for k, v in config_dict.items() if k not in _OAUTH_INTERNAL_KEYS}


@dataclass
class Session:
    cloud_name: str
    access_token: str
    refresh_token: str = None
    issued_at: int = 0
    expires_at: int = 0
    region: str = "api"
    issuer: str = None

    def is_fresh(self, skew=OAUTH_EXPIRY_SKEW_SECONDS):
        return int(self.expires_at or 0) - skew > int(time.time())

    @classmethod
    def from_token_response(cls, token_response, cloud_name=None, region="api"):
        # exp/iat come from the token's JWT claims, not the local clock.
        access_token = token_response["access_token"]
        claims = _decode_jwt_payload(access_token)
        cloud_name = cloud_name or _claim_cloud_name(claims)
        if not cloud_name:
            raise ValueError("OAuth access token has no cloud name (ext.cloud_name claim); "
                             "cannot perform requests without it")
        return cls(
            cloud_name=cloud_name,
            access_token=access_token,
            refresh_token=token_response.get("refresh_token"),
            issued_at=_required_claim(claims, "iat"),
            expires_at=_required_claim(claims, "exp"),
            region=region,
            issuer=claims.get("iss"),
        )

    def updated_from(self, token_response):
        """Return a new Session with refreshed tokens, preserving cloud_name/region."""
        return Session.from_token_response(
            token_response, cloud_name=self.cloud_name, region=self.region)


def to_cloudinary_url(session):
    """Encode a Session as a key-less cloudinary:// URL (Bearer auth, region-derived host)."""
    params = {
        "oauth_token": session.access_token,
        "refresh_token": session.refresh_token or "",
        "issued_at": session.issued_at,
        "expires_at": session.expires_at,
        "region": session.region,
        "issuer": session.issuer or "",
        "upload_prefix": api_host_for_region(session.region),
    }
    return f"cloudinary://{session.cloud_name}?{urllib.parse.urlencode(params)}"


def from_cloudinary_url(url):
    """Parse an OAuth cloudinary:// URL back into a Session."""
    parsed = urllib.parse.urlparse(url)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    return Session(
        cloud_name=parsed.hostname,
        access_token=q.get("oauth_token"),
        refresh_token=q.get("refresh_token") or None,
        issued_at=int(q.get("issued_at", 0) or 0),
        expires_at=int(q.get("expires_at", 0) or 0),
        region=q.get("region", "api"),
        issuer=q.get("issuer") or None,
    )


def is_oauth_url(url):
    if not isinstance(url, str):
        return False
    query = urllib.parse.urlparse(url).query
    return _OAUTH_MARKER in urllib.parse.parse_qs(query)


def _decode_jwt_payload(access_token):
    """Decode the (unverified) JWT payload of an access token; raises ValueError on a non-JWT token."""
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad to a multiple of 4
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except (AttributeError, IndexError, ValueError) as e:
        raise ValueError(f"OAuth access token is not a decodable JWT: {e}") from e


def _required_claim(claims, name):
    value = claims.get(name)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"OAuth access token has a missing or non-numeric '{name}' claim: {value!r}") from None


def _claim_cloud_name(claims):
    return (claims.get("ext") or {}).get("cloud_name")
