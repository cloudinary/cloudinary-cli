#!/usr/bin/env python3
import os
import re
import time
from datetime import datetime, timezone

import cloudinary
from click import echo
from cloudinary import api
from filelock import FileLock

from cloudinary_cli.defaults import (
    CLOUDINARY_CLI_CONFIG_FILE,
    OLD_CLOUDINARY_CLI_CONFIG_FILE,
    DEFAULT_CONFIG_KEY,
    logger,
)
from cloudinary_cli.utils.json_utils import write_json_to_file, read_json_from_file
from cloudinary_cli.utils.utils import log_exception

# Cross-process lock guarding read-modify-write of the config file. Reentrant within a process,
# so callers may hold it across a multi-step update (e.g. token refresh) without deadlocking.
_config_lock = FileLock(CLOUDINARY_CLI_CONFIG_FILE + ".lock")


def config_lock():
    # The lock file lives in the config dir, which may not exist yet on a fresh install.
    _verify_file_path(CLOUDINARY_CLI_CONFIG_FILE)
    return _config_lock


# Parsed-config cache keyed on the file's (mtime_ns, size). The config file is read on nearly every
# code path; caching skips the re-read + JSON parse when it has not changed on disk (including
# changes written by a peer process, which os.replace stamps with a new mtime).
_config_cache = None
_config_cache_stat = None


def _config_stat():
    try:
        st = os.stat(CLOUDINARY_CLI_CONFIG_FILE)
        return st.st_mtime_ns, st.st_size
    except FileNotFoundError:
        return None


def _invalidate_config_cache():
    global _config_cache, _config_cache_stat
    _config_cache = None
    _config_cache_stat = None


def load_config():
    global _config_cache, _config_cache_stat
    stat = _config_stat()
    if stat is not None and stat == _config_cache_stat and _config_cache is not None:
        return dict(_config_cache)  # copy: callers mutate the result in place (e.g. cfg.update(...))
    cfg = read_json_from_file(CLOUDINARY_CLI_CONFIG_FILE, does_not_exist_ok=True)
    _config_cache, _config_cache_stat = cfg, stat
    return dict(cfg)


def save_config(config):
    # 0600 from the start: the config file holds secrets (api_secret, account_url, OAuth tokens),
    # and writing the temp file 0600 before the atomic replace means it is never momentarily
    # world-readable (unlike a chmod applied after the replace).
    _verify_file_path(CLOUDINARY_CLI_CONFIG_FILE)
    write_json_to_file(config, CLOUDINARY_CLI_CONFIG_FILE, atomic=True, mode=0o600)
    _invalidate_config_cache()  # next load_config re-stats and reloads our own write


def update_config(new_config):
    with config_lock():
        curr_config = load_config()
        curr_config.update(new_config)
        save_config(curr_config)


def remove_config_keys(*keys):
    with config_lock():
        curr_config = load_config()
        not_found = []
        for key in keys:
            if not curr_config.pop(key, None):
                not_found.append(key)

        save_config(curr_config)

    return not_found


def get_default_config_name():
    """Return the stored default config name, or None if none is set."""
    return load_config().get(DEFAULT_CONFIG_KEY)


def set_default_config(name):
    update_config({DEFAULT_CONFIG_KEY: name})


def clear_default_config():
    remove_config_keys(DEFAULT_CONFIG_KEY)


def user_config_names(cfg=None):
    """Saved config names with the reserved default key filtered out."""
    cfg = cfg if cfg is not None else load_config()
    return [k for k in cfg if k != DEFAULT_CONFIG_KEY]


def is_reserved_config_name(name):
    """Names wrapped in double underscores are reserved for internal keys (e.g. the default)."""
    return name.startswith("__") and name.endswith("__")


def refresh_cloudinary_config(cloudinary_url, saved_name=None):
    """Install cloudinary_url as the active config. OAuth URLs install a self-refreshing config
    bound to saved_name (so token rotations persist); other URLs use the plain SDK config."""
    from cloudinary_cli.auth.oauth_config import install_oauth_config
    install_oauth_config(cloudinary_url, saved_name=saved_name)


def verify_cloudinary_url(cloudinary_url):
    refresh_cloudinary_config(cloudinary_url)
    return ping_cloudinary()


def config_to_dict(config):
    return {k: v for k, v in config.__dict__.items() if not k.startswith("_")}


def cloud_name_from_url(url):
    """Parse a saved cloudinary:// URL and return its cloud name, or "" if it cannot be parsed."""
    config_obj = cloudinary.Config()
    try:
        # noinspection PyProtectedMember
        config_obj._setup_from_parsed_url(config_obj._parse_cloudinary_url(url))
    except Exception:
        return ""
    return config_obj.cloud_name or ""


def config_type(url):
    """Classify a saved config URL as "oauth" or "api_key"."""
    from cloudinary_cli.auth.session import is_oauth_url
    return "oauth" if is_oauth_url(url) else "api_key"


_SECRET_KEYS = {"api_secret", "oauth_token", "refresh_token"}
_URL_SECRET_KEYS = {"account_url"}
# Fixed mask width so a long secret (e.g. an OAuth JWT) does not print a wall of asterisks and the
# real length is not leaked. The last 4 chars are kept as a fingerprint to identify the value.
_MASK_PREFIX = "****"


def _mask_secret(value):
    value = str(value)
    return _MASK_PREFIX + value[-4:] if len(value) > 4 else "*" * len(value)


def _mask_url_secret(url):
    # Mask the password between `:` and `@` in scheme://user:secret@host.
    return re.sub(r'(://[^:/?#]+:)([^@]+)(@)',
                  lambda m: m.group(1) + _mask_secret(m.group(2)) + m.group(3), str(url))


# account://<provisioning_api_key>:<provisioning_api_secret>@<account_id>
_ACCOUNT_URL_RE = re.compile(r'^account://([^:/?#]+):([^@]+)@(.+)$')


def _format_account_url(url):
    """Render the provisioning account URL as a labeled, secret-masked block (or None if unparsable)."""
    match = _ACCOUNT_URL_RE.match(str(url))
    if not match:
        return None
    api_key, api_secret, account_id = match.groups()
    fields = {
        "account_id": account_id,
        "provisioning_api_key": api_key,
        "provisioning_api_secret": _mask_secret(api_secret),
    }
    width = len(max(fields, key=len)) + 1
    template = "{0:" + str(width) + "} {1}"
    return "\n".join(template.format(f"{k}:", v) for k, v in fields.items())


def _format_expires_at(value):
    # OAuth token expiry: show the raw epoch plus a human-readable UTC time and live/expired state.
    try:
        epoch = int(value)
    except (TypeError, ValueError):
        return value
    human = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    state = "expired" if epoch <= int(time.time()) else "valid"
    return f"{epoch} ({human}, {state})"


def show_cloudinary_config(cloudinary_config):
    obfuscated_config = config_to_dict(cloudinary_config)

    # omit default signature algorithm
    if obfuscated_config.get("signature_algorithm", None) == cloudinary.utils.SIGNATURE_SHA1:
        obfuscated_config.pop("signature_algorithm")

    # The account URL is long and structurally distinct, so it is shown in its own section below.
    account_url = obfuscated_config.pop("account_url", None)

    obfuscated_config = {
        key: _display_value(key, value)
        for key, value in obfuscated_config.items()
        if value not in (None, "")  # drop empty/None fields (e.g. api_key on an OAuth config)
    }

    if not obfuscated_config and not account_url:
        return False

    if obfuscated_config:
        width = len(max(obfuscated_config, key=len)) + 1
        template = "{0:" + str(width) + "} {1}"
        echo('\n'.join([template.format(f"{k}:", v) for k, v in obfuscated_config.items()]))

    if account_url:
        structured = _format_account_url(account_url)
        if structured is not None:
            echo(f"\nAccount (provisioning) API:\n{structured}")
        else:
            echo(f"\naccount_url: {_mask_url_secret(account_url)}")


def cloudinary_config_details(cloudinary_config):
    """
    JSON-friendly, secret-masked view of a Cloudinary config: the same fields shown by
    show_cloudinary_config, with secrets masked, empties dropped, expires_at expanded into a
    structured object, and account_url decomposed into a nested `account` object.
    """
    raw = config_to_dict(cloudinary_config)

    if raw.get("signature_algorithm", None) == cloudinary.utils.SIGNATURE_SHA1:
        raw.pop("signature_algorithm")

    account_url = raw.pop("account_url", None)

    details = {}
    for key, value in raw.items():
        if value in (None, ""):
            continue
        if key in _SECRET_KEYS:
            details[key] = _mask_secret(value)
        elif key == "expires_at":
            details[key] = _expires_at_details(value)
        else:
            details[key] = value

    account = _account_url_details(account_url) if account_url else None
    if account is not None:
        details["account"] = account
    elif account_url:
        details["account_url"] = _mask_url_secret(account_url)

    return details


def _expires_at_details(value):
    try:
        epoch = int(value)
    except (TypeError, ValueError):
        return value
    return {
        "epoch": epoch,
        "utc": datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "expired": epoch <= int(time.time()),
    }


def _account_url_details(url):
    match = _ACCOUNT_URL_RE.match(str(url))
    if not match:
        return None
    api_key, api_secret, account_id = match.groups()
    return {
        "account_id": account_id,
        "provisioning_api_key": api_key,
        "provisioning_api_secret": _mask_secret(api_secret),
    }


def _display_value(key, value):
    if key in _SECRET_KEYS:
        return _mask_secret(value)
    if key == "expires_at":
        return _format_expires_at(value)
    return value


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
    config = cloudinary.config()
    # has_oauth reports token presence without triggering OAuthConfig's refresh-on-read. Fall back
    # to a refresh-free __dict__ read for a plain SDK Config (e.g. before any config is installed).
    has_oauth = config.has_oauth if hasattr(config, "has_oauth") else bool(config.__dict__.get("oauth_token"))
    if config.cloud_name and has_oauth:
        return True
    return None not in [config.cloud_name, config.api_key, config.api_secret]


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
