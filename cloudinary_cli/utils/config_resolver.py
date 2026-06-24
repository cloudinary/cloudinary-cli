#!/usr/bin/env python3
import cloudinary

from cloudinary_cli.auth import refresh_url_if_stale
from cloudinary_cli.auth.session import strip_oauth_internal_keys
from cloudinary_cli.defaults import logger, DEFAULT_CONFIG_KEY
from cloudinary_cli.utils.config_utils import (
    load_config,
    config_to_dict,
    ping_cloudinary,
    refresh_cloudinary_config,
    is_valid_cloudinary_config,
    is_env_configured,
    user_config_names,
)

_UNCONFIGURED_MESSAGE = (
    "No Cloudinary configuration found.\n"
    "  - Log in with OAuth:        cld login\n"
    "  - Add an API-key config:    cld config -n <name> "
    "cloudinary://<api_key>:<api_secret>@<cloud_name> --set-default\n"
    "  - Set an existing config\n"
    "    as the default:           cld config -d <name>"
)

# What the last resolve_cli_config (Phase A) selected, by precedence. One of:
#   "url"   -> an inline -c CLOUDINARY_URL
#   "env"   -> the environment fallback
#   None    -> nothing configured
# plus _active_name, the saved-config name when a -C/default saved entry was selected (else None).
# Read by ensure_active_config_fresh (Phase B) to know which saved login may need a lazy refresh,
# and by `config -ls` to mark the row that is actually active for this invocation.
_active_name = None
_active_source = None


def resolve_cli_config(config=None, config_saved=None):
    """Select a config by precedence and load it into the SDK global. No network I/O."""
    global _active_name, _active_source
    _active_name = None
    _active_source = None

    if config:
        _active_source = "url"
        refresh_cloudinary_config(config)
        return _format_ok()

    cfg = load_config()

    if config_saved:
        if config_saved not in user_config_names(cfg):
            raise Exception(f"Config {config_saved} does not exist")
        _active_name = config_saved
        _active_source = "saved"
        refresh_cloudinary_config(cfg[config_saved])
        return _format_ok()

    default = cfg.get(DEFAULT_CONFIG_KEY)
    if default and default in cfg:
        _active_name = default
        _active_source = "saved"
        refresh_cloudinary_config(cfg[default])
        return _format_ok()

    # No stored default: the SDK global already holds the environment config (if any), so
    # _format_ok validates it; otherwise it warns that nothing is configured.
    if is_env_configured():
        _active_source = "env"
    return _format_ok()


def active_config_name():
    """The saved-config name selected by the last resolution, or None for -c/env/unconfigured."""
    return _active_name


def active_config_is_env():
    """True when the last resolution fell through to the environment fallback."""
    return _active_source == "env"


def active_config_is_url():
    """True when the last resolution loaded an inline -c CLOUDINARY_URL."""
    return _active_source == "url"


def _format_ok():
    """Format-only check: is a usable-SHAPED config loaded? Does NOT contact the network."""
    if not is_valid_cloudinary_config():
        logger.warning(_UNCONFIGURED_MESSAGE)
        return False
    return True


def ensure_active_config_fresh():
    """Refresh the active OAuth token if stale, just before an API call. No-op otherwise."""
    name = _active_name
    if name is None:
        return
    url = load_config().get(name)
    if url is None:
        return
    fresh = refresh_url_if_stale(name, url)
    if fresh != url:
        refresh_cloudinary_config(fresh)


def get_cloudinary_config(target):
    target_config = cloudinary.Config()
    if target.startswith("cloudinary://"):
        parsed_url = target_config._parse_cloudinary_url(target)
    elif target in load_config():
        url = refresh_url_if_stale(target, load_config().get(target))
        parsed_url = target_config._parse_cloudinary_url(url)
    else:
        return False

    target_config._setup_from_parsed_url(parsed_url)

    if not ping_cloudinary(**config_to_api_kwargs(target_config)):
        logger.error(f"Invalid Cloudinary config: {target}")
        return False

    return target_config


def config_to_api_kwargs(config):
    return strip_oauth_internal_keys(config_to_dict(config))
