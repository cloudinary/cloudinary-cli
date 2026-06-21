#!/usr/bin/env python3
import cloudinary

from cloudinary_cli.auth import refresh_url_if_stale, find_sole_oauth_login
from cloudinary_cli.auth.session import strip_oauth_internal_keys
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import (
    load_config,
    config_to_dict,
    ping_cloudinary,
    refresh_cloudinary_config,
    is_valid_cloudinary_config,
    is_env_configured,
)


def resolve_cli_config(config=None, config_saved=None):
    explicit_config = bool(config or config_saved) or is_env_configured()

    if config:
        refresh_cloudinary_config(config)
    elif config_saved:
        saved = load_config()
        if config_saved not in saved:
            raise Exception(f"Config {config_saved} does not exist")
        refresh_cloudinary_config(refresh_url_if_stale(config_saved, saved[config_saved]))

    if not explicit_config and not is_valid_cloudinary_config():
        sole_login = find_sole_oauth_login()
        if sole_login:
            name, url = sole_login
            refresh_cloudinary_config(refresh_url_if_stale(name, url))

    if not is_valid_cloudinary_config():
        logger.warning("No Cloudinary configuration found.")
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
