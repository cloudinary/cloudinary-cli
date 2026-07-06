#!/usr/bin/env python3
import cloudinary
from click import UsageError, echo

from cloudinary_cli.auth import refresh_url_if_stale
from cloudinary_cli.auth.session import strip_oauth_internal_keys
from cloudinary_cli.defaults import (
    logger,
    DEFAULT_CONFIG_KEY,
    NO_CONFIG_MESSAGE,
    NO_DEFAULT_CONFIG_MESSAGE,
    INCOMPLETE_CONFIG_MESSAGE,
)
from cloudinary_cli.utils.config_utils import (
    load_config,
    config_to_dict,
    ping_cloudinary,
    refresh_cloudinary_config,
    is_valid_cloudinary_config,
    is_env_configured,
    user_config_names,
    validate_config_url,
)

# What the last resolve_cli_config selected, by precedence. One of:
#   "url"   -> an inline -c CLOUDINARY_URL
#   "env"   -> the environment fallback
#   None    -> nothing configured
# plus _active_name, the saved-config name when a -C/default saved entry was selected (else None),
# read by `config -ls` to mark the row active for this invocation. Token freshness is no longer
# handled here: a saved OAuth config installs a self-refreshing OAuthConfig that refreshes lazily
# when the SDK reads its oauth_token at request time.
_active_name = None
_active_source = None


def resolve_cli_config(config=None, config_saved=None, warn_if_unconfigured=True):
    """Select a config by precedence and load it into the SDK global. No network I/O."""
    global _active_name, _active_source
    _active_name = None
    _active_source = None

    if config and config_saved:
        raise UsageError("-c/--config and -C/--config_saved are mutually exclusive; pass only one.")

    cfg = load_config()

    # -c/-C explicitly select a config; if it is shape-invalid it is incomplete (missing
    # credentials), not absent, so the generic "no config found" guidance would mislead.
    if config:
        _validate_inline_config(config, cfg)
        _active_source = "url"
        refresh_cloudinary_config(config)
        return _format_ok(warn_if_unconfigured, INCOMPLETE_CONFIG_MESSAGE)

    if config_saved:
        if config_saved not in user_config_names(cfg):
            raise Exception(f"Config {config_saved} does not exist")
        _active_name = config_saved
        _active_source = "saved"
        refresh_cloudinary_config(cfg[config_saved], saved_name=config_saved)
        return _format_ok(warn_if_unconfigured, INCOMPLETE_CONFIG_MESSAGE)

    default = cfg.get(DEFAULT_CONFIG_KEY)
    if default and default in cfg:
        _active_name = default
        _active_source = "saved"
        refresh_cloudinary_config(cfg[default], saved_name=default)
        return _format_ok(warn_if_unconfigured)

    # No stored default: fall back to the environment. Install it as an OAuthConfig (static, no
    # saved name -> never refreshes) so the active global is always an OAuthConfig and exposes
    # has_oauth uniformly; if nothing is configured, _format_ok warns.
    if is_env_configured():
        _active_source = "env"
        from cloudinary_cli.auth.oauth_config import install_env_config
        install_env_config()
        return _format_ok(warn_if_unconfigured)

    # Nothing resolved. If saved configs exist, the account is there but no default is set, so guide
    # the user to pick one rather than claiming there is no configuration at all.
    message = NO_DEFAULT_CONFIG_MESSAGE if user_config_names(cfg) else NO_CONFIG_MESSAGE
    return _format_ok(warn_if_unconfigured, message)


def active_config_name():
    """The saved-config name selected by the last resolution, or None for -c/env/unconfigured."""
    return _active_name


def active_config_is_env():
    """True when the last resolution fell through to the environment fallback."""
    return _active_source == "env"


def active_config_is_url():
    """True when the last resolution loaded an inline -c CLOUDINARY_URL."""
    return _active_source == "url"


def _validate_inline_config(config, cfg):
    """-c/--config takes a CLOUDINARY_URL, not a saved config name. Fail early with a clear message
    (and point at -C when the value matches a saved config) instead of letting a malformed value
    surface as a raw SDK error deep inside command execution."""
    try:
        validate_config_url(config)
    except ValueError as e:
        if config in user_config_names(cfg):
            raise UsageError(f"-c/--config expects a CLOUDINARY_URL, but '{config}' is a saved "
                             f"configuration name. Select it with -C/--config_saved instead: "
                             f"cld -C {config} <command>.")
        raise UsageError(f"-c/--config expects a CLOUDINARY_URL "
                         f"(cloudinary://<api_key>:<api_secret>@<cloud_name>): {e}")


def _format_ok(warn=True, message=NO_CONFIG_MESSAGE):
    """Format-only check: is a usable-SHAPED config loaded? Does NOT contact the network."""
    if not is_valid_cloudinary_config():
        if warn:
            echo(message, err=True)
        return False
    return True


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
