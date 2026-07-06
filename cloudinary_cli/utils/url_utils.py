"""Generic URL query-string helpers — the single place that touches urllib for reading/writing query
params and hosts. Knows nothing about Cloudinary; the cloudinary:// config codec lives in config_utils."""
from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qs


def url_params(url):
    """The URL's query string as a flat {key: value} dict (first value per key), or {} if none."""
    query = urlsplit(url or "").query
    return {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}


def url_param(url, key):
    """A single query param value from the URL, or None if absent."""
    return url_params(url).get(key)


def url_host(url):
    """The host (netloc without userinfo/port) of a URL."""
    return urlsplit(url or "").hostname


def set_url_params(url, **params):
    """Return url with the given query params added or overridden. Values are urlencoded, so an '@'
    in a value never collides with the userinfo '@'. Existing params are preserved."""
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    for key, value in params.items():
        query[key] = [value]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))
