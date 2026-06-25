#!/usr/bin/env python3
import cloudinary

from cloudinary_cli.auth.session import is_oauth_url, from_cloudinary_url


class OAuthConfig(cloudinary.Config):
    """
    A Cloudinary config whose `oauth_token` refreshes itself on read, at the moment the SDK builds
    a request. Presence/type checks read `has_oauth` instead and never touch the network, so offline
    paths (`config -ls`, `config -s`, the group-level validity check) stay offline.

    The raw access token is kept in `__dict__["oauth_token"]` so serialization (config_to_dict,
    masking) still sees it; the class-level property shadows it on attribute *read* to
    refresh-if-stale. A parsed Session (`_session`) carries expiry/refresh-token so a still-fresh
    token short-circuits with no disk read and no lock — only a stale token reads config + refreshes.
    """

    def bind_saved(self, name, url):
        # name: the saved-config name this maps to (None for env / inline -c -> never refreshes).
        # url:  the full cloudinary:// URL, kept parsed so we know expiry without re-reading disk.
        self._saved_name = name
        self._session = from_cloudinary_url(url) if (name and url and is_oauth_url(url)) else None

    @classmethod
    def from_env(cls):
        """An OAuthConfig populated from the environment (CLOUDINARY_URL/CLOUDINARY_*). Static: it is
        not bound to a saved name, so reading its oauth_token never refreshes."""
        cfg = cls()  # the base Config constructor loads the environment
        cfg._saved_name = None
        cfg._session = None
        return cfg

    @classmethod
    def from_url(cls, url):
        """An OAuthConfig populated from a cloudinary:// URL, not bound to a saved name (static)."""
        cfg = cls()
        cfg._load_from_url(url)
        cfg._saved_name = None
        cfg._session = None
        return cfg

    @property
    def has_oauth(self):
        """True if this config carries an OAuth token. Cheap, never refreshes."""
        return bool(self.__dict__.get("oauth_token"))

    @property
    def oauth_token(self):
        session = getattr(self, "_session", None)
        if session is None:
            return self.__dict__.get("oauth_token")  # env / -c / api-key: static, no refresh
        if session.is_fresh() or not session.refresh_token:
            return self.__dict__.get("oauth_token")  # still valid (or unrefreshable): no I/O

        # Stale: read the saved URL (a peer may already have refreshed it) and refresh under lock.
        from cloudinary_cli.auth import refresh_url_if_stale
        from cloudinary_cli.utils.config_utils import load_config

        url = load_config().get(self._saved_name)
        if not url:
            return self.__dict__.get("oauth_token")  # config removed underneath us; serve what we have
        fresh_url = refresh_url_if_stale(self._saved_name, url)
        self._session = from_cloudinary_url(fresh_url)
        self.__dict__["oauth_token"] = self._session.access_token
        return self.__dict__["oauth_token"]

    @oauth_token.setter
    def oauth_token(self, value):
        self.__dict__["oauth_token"] = value


def install_oauth_config(cloudinary_url, saved_name=None):
    """
    Load `cloudinary_url` and install it as the active SDK config. The installed object is always an
    OAuthConfig (so every active config exposes `has_oauth`); it self-refreshes only when bound to a
    saved OAuth `saved_name`, and is static for api-key / inline `-c` URLs. The single seam that
    swaps the global config object.
    """
    cloudinary.reset_config()
    cfg = OAuthConfig()
    cfg._load_from_url(cloudinary_url)
    cfg.bind_saved(saved_name, cloudinary_url)
    cloudinary._config = cfg
    return cfg


def install_env_config():
    """Install the environment config as a (static) OAuthConfig, so the active global is always an
    OAuthConfig and exposes has_oauth without a refresh. Used for the env fallback branch."""
    cfg = OAuthConfig.from_env()
    cloudinary._config = cfg
    return cfg
