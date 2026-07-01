#!/usr/bin/env python3
"""Presentation of the saved-config inventory: the rows behind `config -ls`, the table renderer,
and the per-config metadata used for `config`/`config -s` (text headers and JSON)."""
import cloudinary

from cloudinary_cli.auth.oauth_config import OAuthConfig
from cloudinary_cli.defaults import DEFAULT_CONFIG_KEY
from cloudinary_cli.utils.config_utils import (
    load_config,
    user_config_names,
    cloud_name_from_url,
    config_type,
    cloudinary_config_details,
    is_env_configured,
    email_from_url,
)
from cloudinary_cli.utils.config_resolver import (
    active_config_name,
    active_config_is_env,
    active_config_is_url,
)

# Display names for the synthetic (non-saved) configs. Parenthesized so they read as a source
# label, not a saved config name, in both the table and JSON.
SYNTHETIC_NAMES = {"env": "(environment)", "url": "(command-line)"}


def config_type_label(config_obj):
    """oauth/api_key for a config OBJECT. Every active config the CLI installs is an OAuthConfig, so
    presence is read via has_oauth (refresh-free). (config_utils.config_type classifies a URL str.)"""
    return "oauth" if config_obj.has_oauth else "api_key"

_TABLE_COLUMNS = [("name", "NAME"), ("cloud_name", "CLOUD"), ("type", "TYPE"),
                  ("default", "DEFAULT"), ("active", "ACTIVE")]
# EMAIL is appended dynamically (see render_config_table) only when at least one row carries one.
_EMAIL_COLUMN = ("email", "EMAIL")


def list_configs():
    cfg = load_config()
    # "default" is the persistent user choice (-d); "active" is the config this very invocation
    # resolved to (honoring -c/-C/default/env precedence), as recorded by the resolver.
    default = cfg.get(DEFAULT_CONFIG_KEY)
    active_name = active_config_name()

    rows = []
    if active_config_is_url():
        rows.append(_url_row())  # an inline -c URL: not a saved config, but it is what's active now
    if is_env_configured():
        rows.append(_env_row(env_active=active_config_is_env()))
    for name in user_config_names(cfg):
        row = {
            "name": name,
            "cloud_name": cloud_name_from_url(cfg[name]),
            "type": config_type(cfg[name]),
            "source": "saved",
            "default": name == default,
            "active": name == active_name,
        }
        email = email_from_url(cfg[name])
        if email:  # only surfaced when the config records an account email (e.g. from `agent signup`)
            row["email"] = email
        rows.append(row)
    return rows


def config_meta(name, cfg, config_obj):
    """JSON view of a named saved config: header metadata plus the masked detail fields."""
    return {
        "name": name,
        "source": "saved",
        "type": config_type(cfg[name]),
        "default": cfg.get(DEFAULT_CONFIG_KEY) == name,
        "active": active_config_name() == name,
        **cloudinary_config_details(config_obj),
    }


def active_config_meta(config_obj):
    """JSON view of the active config for bare `cld config` (saved name, -c URL, or env)."""
    name = active_config_name()
    if name is not None:
        return config_meta(name, load_config(), config_obj)
    source = "url" if active_config_is_url() else "env"
    return {
        "name": SYNTHETIC_NAMES[source],
        "source": source,
        "type": config_type_label(config_obj),
        "default": False,
        "active": True,
        **cloudinary_config_details(config_obj),
    }


def render_config_table(rows):
    columns = list(_TABLE_COLUMNS)
    if any(row.get("email") for row in rows):  # add EMAIL only when some config records one
        columns.append(_EMAIL_COLUMN)
    headers = [title for _, title in columns]
    cells = [[_cell(row, key) for key, _ in columns] for row in rows]
    widths = [max(len(headers[i]), *(len(r[i]) for r in cells)) if cells else len(headers[i])
              for i in range(len(headers))]
    line = lambda values: "  ".join(v.ljust(widths[i]) for i, v in enumerate(values)).rstrip()
    return "\n".join([line(headers)] + [line(r) for r in cells])


def _url_row():
    active = cloudinary.config()  # the CLI global, which the resolver loaded from the -c URL
    return {
        "name": SYNTHETIC_NAMES["url"],
        "cloud_name": active.cloud_name or "",
        "type": config_type_label(active),
        "source": "url",
        "default": False,  # an inline URL is never the stored default
        "active": True,    # it outranks everything else for this invocation
    }


def _env_row(env_active):
    env_config = OAuthConfig.from_env()  # constructed fresh from the environment, not the CLI global
    return {
        "name": SYNTHETIC_NAMES["env"],
        "cloud_name": env_config.cloud_name or "",
        "type": config_type_label(env_config),
        "source": "env",
        "default": False,       # the environment is never the *stored* default
        "active": env_active,   # active only when no stored default outranks it
    }


def _cell(row, key):
    if key in ("default", "active"):
        return "*" if row[key] else ""
    return str(row.get(key) or "")
