#!/usr/bin/env python3
import threading

import cloudinary
from cloudinary.exceptions import AuthorizationRequired

from cloudinary_cli.auth.session import is_oauth_url, from_cloudinary_url
from cloudinary_cli.auth.refresh import refresh_url_if_stale
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils import config_utils
from cloudinary_cli.utils.utils import token_hint


class OAuthConfig(cloudinary.Config):
    """
    A Cloudinary config whose `oauth_token` refreshes itself on read. Presence/type checks read
    `has_oauth` instead, which never touches the network, so offline paths stay offline.

    Rotation single-flights: the first worker to see a token invalid (clock-stale, a peer rotated on
    disk, or a 401) takes `_refresh_lock` and rotates once; the rest adopt the result. The decision is
    keyed on the specific token a worker saw invalid, not the clock, so a token a peer already replaced
    is adopted rather than re-rotated (burning a single-use refresh token). Static configs (env /
    inline `-c` / api-key, `_session` is None) never refresh.
    """

    def _init_oauth_state(self, name, session):
        self._saved_name = name  # None for static configs: they never refresh
        self._session = session
        self._session_mtime = config_utils.config_mtime()  # a later config mtime = a peer rotated on disk
        self._refresh_lock = threading.Lock()

    @property
    def oauth_token_refresh_callback(self):
        # SDK hook (uploader.upload_large): rotate on a chunk 401, retrying the chunk to resume.
        # A property (not a __dict__ entry) so it stays out of config serialization, which dumps
        # the public keys of __dict__.
        return self._refresh_for_sdk

    def _refresh_for_sdk(self, rejected):
        # invalidate_token returns False when no usable token results (static config, dead refresh);
        # the SDK contract signals that by raising, so the rejected token is not retried.
        logger.debug(f"Upload chunk got a 401 on token {token_hint(rejected)}; attempting OAuth refresh")
        if not self.invalidate_token(rejected):
            logger.debug(f"OAuth refresh did not yield a new token for {token_hint(rejected)}; chunk upload fails")
            raise AuthorizationRequired("OAuth token refresh produced no usable token")
        logger.debug(f"OAuth token refreshed to {token_hint(self.__dict__.get('oauth_token'))}; retrying upload chunk")

    def bind_saved(self, name, url):
        session = from_cloudinary_url(url) if (name and url and is_oauth_url(url)) else None
        self._init_oauth_state(name, session)

    @classmethod
    def from_env(cls):
        """An OAuthConfig from the environment. Static: never refreshes."""
        cfg = cls()
        cfg._init_oauth_state(None, None)
        return cfg

    @classmethod
    def from_url(cls, url):
        """An OAuthConfig from a cloudinary:// URL, not bound to a saved name. Static: never refreshes."""
        cfg = cls()
        cfg._load_from_url(url)
        cfg._init_oauth_state(None, None)
        return cfg

    @property
    def has_oauth(self):
        """True if this config carries an OAuth token. Cheap, never refreshes."""
        return bool(self.__dict__.get("oauth_token"))

    def _is_invalid(self, session):
        if not session.refresh_token:
            return False  # unrefreshable: serve it and let it fail
        return not session.is_fresh() or config_utils.config_mtime() > self._session_mtime

    @property
    def oauth_token(self):
        session = getattr(self, "_session", None)
        if session is None or not self._is_invalid(session):
            return self.__dict__.get("oauth_token")

        stale_token = self.__dict__.get("oauth_token")
        with self._refresh_lock:
            if self.__dict__.get("oauth_token") != stale_token:
                return self.__dict__.get("oauth_token")  # a peer rotated while we waited; adopt it
            return self._refresh_locked(stale_token)

    def _refresh_locked(self, stale_token):
        # Caller holds _refresh_lock. Rotates only while disk still holds `stale_token`, else adopts.
        url = config_utils.load_config().get(self._saved_name)
        if not url:
            return self.__dict__.get("oauth_token")  # config removed underneath us; serve what we have
        url = refresh_url_if_stale(self._saved_name, url, expected=stale_token)
        self._session = from_cloudinary_url(url)
        self.__dict__["oauth_token"] = self._session.access_token
        self._session_mtime = config_utils.config_mtime()
        return self.__dict__["oauth_token"]

    @oauth_token.setter
    def oauth_token(self, value):
        self.__dict__["oauth_token"] = value

    def invalidate_token(self, rejected):
        """
        Recover after the server rejected `rejected` (AuthorizationRequired): adopt a peer's rotated
        token, else rotate once, keyed on `rejected` so an old-token rejection adopts rather than
        re-rotates. Returns True when a usable token is now in place; False for static configs.
        """
        if not (getattr(self, "_session", None) and getattr(self, "_saved_name", None)):
            return False
        with self._refresh_lock:
            if self.__dict__.get("oauth_token") != rejected:
                return True  # a peer already rotated; adopt it
            self._refresh_locked(rejected)
            return self.__dict__.get("oauth_token") != rejected


def install_oauth_config(cloudinary_url, saved_name=None):
    """
    Load `cloudinary_url` and install it as the active SDK config. The installed object is always an
    OAuthConfig (so every active config exposes `has_oauth`); it self-refreshes only when bound to a
    saved OAuth `saved_name`, and is static for api-key / inline `-c` URLs.
    """
    cloudinary.reset_config()
    cfg = OAuthConfig()
    cfg._load_from_url(cloudinary_url)
    cfg.bind_saved(saved_name, cloudinary_url)
    cloudinary._config = cfg
    return cfg


def install_env_config():
    """Install the environment config as a (static) OAuthConfig, so the active global is always an
    OAuthConfig and exposes has_oauth without a refresh."""
    cfg = OAuthConfig.from_env()
    cloudinary._config = cfg
    return cfg
