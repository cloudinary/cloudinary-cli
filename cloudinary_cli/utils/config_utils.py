#!/usr/bin/env python3
import os

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
    os.environ.update({'CLOUDINARY_URL': cloudinary_url})
    cloudinary.reset_config()


def verify_cloudinary_url(cloudinary_url):
    refresh_cloudinary_config(cloudinary_url)
    return ping_cloudinary()


def get_cloudinary_config(target):
    target_config = cloudinary.Config()
    if target.startswith("cloudinary://"):
        parsed_url = target_config._parse_cloudinary_url(target)
    elif target in load_config():
        parsed_url = target_config._parse_cloudinary_url(load_config().get(target))
    else:
        return False

    target_config._setup_from_parsed_url(parsed_url)

    if not ping_cloudinary(**config_to_dict(target_config)):
        logger.error(f"Invalid Cloudinary config: {target}")
        return False

    return target_config

def config_to_dict(config):
    return {k: v for k, v in config.__dict__.items() if not k.startswith("_")}

def show_cloudinary_config(cloudinary_config):
    obfuscated_config = config_to_dict(cloudinary_config)

    if "api_secret" in obfuscated_config:
        api_secret = obfuscated_config["api_secret"]
        obfuscated_config["api_secret"] = "*" * (len(api_secret) - 4) + f"{api_secret[-4:]}"

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
    return None not in [cloudinary.config().cloud_name, cloudinary.config().api_key, cloudinary.config().api_secret]


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
