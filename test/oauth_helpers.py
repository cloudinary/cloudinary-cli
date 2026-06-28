"""Build a real (unsigned) JWT access token. Production reads exp/iat/cloud_name/iss from the token's
claims, so fixtures must carry them rather than use opaque strings."""
import base64
import json
import time

_OMIT = object()  # sentinel: omit the claim entirely (to test the missing-claim path)


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def jwt_access_token(cloud_name="eu-cloud", iat=_OMIT, exp=_OMIT, expires_delta=300,
                     issuer="https://oauth.cloudinary.com/", tag=None):
    """A decodable (unsigned) JWT access token. `iat`/`exp` are absolute epochs, defaulting to
    now / now+expires_delta; pass `None` to omit a claim. `tag` varies the signature so successive
    rotations produce distinct token strings."""
    now = int(time.time())
    iat = now if iat is _OMIT else iat
    exp = (now + expires_delta) if exp is _OMIT else exp
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = {"iss": issuer, "ext": {"cloud_name": cloud_name}}
    if iat is not None:
        claims["iat"] = iat
    if exp is not None:
        claims["exp"] = exp
    payload = _b64url(json.dumps(claims).encode())
    sig = tag if tag is not None else "sig"
    return f"{header}.{payload}.{sig}"
