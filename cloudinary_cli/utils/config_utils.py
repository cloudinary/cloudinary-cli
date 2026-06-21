#!/usr/bin/env python3
import os
import re

import cloudinary
from click import echo
from cloudinary import api

from cloudinary_cli.defaults import CLOUDINARY_CLI_CONFIG_FILE, OLD_CLOUDINARY_CLI_CONFIG_FILE, logger
from cloudinary_cli.utils.json_utils import write_json_to_file, read_json_from_file
from cloudinary_cli.utils.utils import log_exception


def load_config():
    return read_json_from_file(CLOUDINARY_CLI_CONFIG_FILE, does_not_exist_ok=True)


def save_config(config):
    _verify_file_path(CLOUDINARY_CLI_CONFIG_FILE)
    write_json_to_file(config, CLOUDINARY_CLI_CONFIG_FILE)
    _restrict_permissions(CLOUDINARY_CLI_CONFIG_FILE)


def update_config(new_config):
    curr_config = load_config()
    curr_config.update(new_config)
    save_config(curr_config)


def remove_config_keys(*keys):
    curr_config = load_config()
    not_found = []
    for key in keys:
        if not curr_config.pop(key, None):
            not_found.append(key)

    save_config(curr_config)

    return not_found


def refresh_cloudinary_config(cloudinary_url):
    cloudinary.reset_config()
    cloudinary.config()._load_from_url(cloudinary_url)


def verify_cloudinary_url(cloudinary_url):
    refresh_cloudinary_config(cloudinary_url)
    return ping_cloudinary()


def config_to_dict(config):
    return {k: v for k, v in config.__dict__.items() if not k.startswith("_")}


_SECRET_KEYS = {"api_secret", "oauth_token", "refresh_token"}
_URL_SECRET_KEYS = {"account_url"}


def _mask_secret(value):
    value = str(value)
    return "*" * (len(value) - 4) + value[-4:] if len(value) > 4 else "*" * len(value)


def _mask_url_secret(url):
    # Mask the password between `:` and `@` in scheme://user:secret@host.
    return re.sub(r'(://[^:/?#]+:)([^@]+)(@)',
                  lambda m: m.group(1) + _mask_secret(m.group(2)) + m.group(3), str(url))


def show_cloudinary_config(cloudinary_config):
    obfuscated_config = config_to_dict(cloudinary_config)

    for key, value in obfuscated_config.items():
        if value and key in _SECRET_KEYS:
            obfuscated_config[key] = _mask_secret(value)
        elif value and key in _URL_SECRET_KEYS:
            obfuscated_config[key] = _mask_url_secret(value)

    # omit default signature algorithm
    if obfuscated_config.get("signature_algorithm", None) == cloudinary.utils.SIGNATURE_SHA1:
        obfuscated_config.pop("signature_algorithm")

    if not obfuscated_config:
        return False

    template = "{0:" + str(len(max(obfuscated_config, key=len)) + 1) + "} {1}"  # Gets the maximal length of the keys.
    echo('\n'.join([template.format(f"{k}:", v) for k, v in obfuscated_config.items()]))


def migrate_old_config():
    """
    Migrate old config file (if exists) to new location
    """
    if not os.path.exists(OLD_CLOUDINARY_CLI_CONFIG_FILE):
        return

    try:
        old_config = read_json_from_file(OLD_CLOUDINARY_CLI_CONFIG_FILE)
    except Exception:
        logger.error(f"Unable to parse old Cloudinary config file: {OLD_CLOUDINARY_CLI_CONFIG_FILE}, "
                     f"please fix or remove it")
        raise

    update_config(old_config)

    os.remove(OLD_CLOUDINARY_CLI_CONFIG_FILE)


def is_valid_cloudinary_config():
    if cloudinary.config().cloud_name and cloudinary.config().oauth_token:
        return True
    return None not in [cloudinary.config().cloud_name, cloudinary.config().api_key, cloudinary.config().api_secret]


def is_env_configured():
    return bool(cloudinary.Config().cloud_name)


def initialize():
    migrate_old_config()

def ping_cloudinary(**options):
    try:
        api.ping(**options)
    except Exception as e:
        logger.error(f"Failed to ping Cloudinary: {e}")
        return False

    return True

def _verify_file_path(file):
    os.makedirs(os.path.dirname(file), exist_ok=True)


def _restrict_permissions(file):
    # The config file holds secrets (api_secret, account_url, OAuth tokens), so keep it 0600.
    try:
        os.chmod(file, 0o600)
    except OSError as e:
        logger.debug(f"Could not restrict permissions on {file}: {e}")
