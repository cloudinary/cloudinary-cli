import cloudinary
from click import command, option, echo, BadParameter, UsageError

from cloudinary_cli.defaults import logger, DEFAULT_CONFIG_KEY, NO_CONFIG_MESSAGE
from cloudinary_cli.utils.config_utils import (
    load_config,
    verify_cloudinary_url,
    save_named_config,
    remove_config_keys,
    show_cloudinary_config,
    is_valid_cloudinary_config,
    user_config_names,
    get_default_config_name,
    set_default_config,
    clear_default_config,
    is_reserved_config_name,
    config_type,
    config_optional,
)
from cloudinary_cli.utils.utils import ConfigurationError
from cloudinary_cli.utils.json_utils import print_json
from cloudinary_cli.utils.config_resolver import active_config_name, active_config_is_url
from cloudinary_cli.auth import refresh_config, refresh_configs, relogin_command
from cloudinary_cli.utils.config_listing import (
    list_configs,
    render_config_table,
    config_meta,
    active_config_meta,
    config_type_label,
    SYNTHETIC_NAMES,
)


@config_optional
@command("config", help="Display the current configuration, and manage additional configurations.")
@option("-n", "--new", help="""\b Create and name a configuration from a Cloudinary account environment variable.
e.g. cld config -n <NAME> <CLOUDINARY_URL>""", nargs=2)
@option("-ls", "--ls", help="List all saved configurations.", is_flag=True)
@option("-j", "--json", "as_json",
        help="Output as JSON (with -ls, -s, or the bare config view).", is_flag=True)
@option("-s", "--show", help="Show details of a specified configuration.", nargs=1)
@option("-rm", "--rm", help="Delete a specified configuration.", nargs=1)
@option("-url", "--from_url",
        help="Create a configuration from a Cloudinary account environment variable. "
             "The configuration name is the cloud name.",
        nargs=1)
@option("-d", "--default", "default", nargs=1,
        help="Set the named saved configuration as the default.")
@option("--set-default", "set_default", is_flag=True,
        help="Set the configuration created by this command (-n / --from_url) as the default.")
@option("-ud", "--unset-default", "unset_default", is_flag=True,
        help="Clear the stored default configuration.")
@option("-r", "--refresh", "refresh", nargs=1,
        help="Refresh the OAuth token of a saved configuration (use the active config if no name).",
        is_flag=False, flag_value="")
@option("-ra", "--refresh-all", "refresh_all", is_flag=True,
        help="Refresh every saved OAuth configuration whose token is stale.")
@option("-f", "--force", "force", is_flag=True,
        help="With --refresh/--refresh-all, refresh even tokens that are still fresh.")
def config_command(new, ls, as_json, show, rm, from_url, default, set_default, unset_default,
                   refresh, refresh_all, force):
    if set_default and not (new or from_url):
        raise UsageError("--set-default requires -n or --from_url; "
                         "to default an existing config use -d <name>.")

    if force and refresh is None and not refresh_all:
        raise UsageError("--force only applies to --refresh or --refresh-all.")

    if refresh_all:
        return _refresh_all(force)
    if refresh is not None:
        return _refresh_one(refresh, force)

    if new or from_url:
        config_name, cloudinary_url = new or [None, from_url]

        if config_name and is_reserved_config_name(config_name):
            raise BadParameter(f"'{config_name}' is a reserved configuration name.")

        if not verify_cloudinary_url(cloudinary_url):
            return False

        config_name = config_name or cloudinary.config().cloud_name

        default_status = save_named_config(config_name, cloudinary_url, set_default=set_default)

        logger.info("Config '{}' saved!".format(config_name))
        logger.info("Example usage: cld -C {} <command>".format(config_name))

        if default_status == "made":
            logger.info(f"Default set to '{config_name}'. Run `cld <command>` to use it, "
                        f"or `cld -C {config_name} <command>` to select it explicitly.")
    elif default:
        if default not in user_config_names(load_config()):
            raise BadParameter(f"Configuration {default} does not exist, "
                               f"use -ls to list available configurations.")
        set_default_config(default)
        logger.info(f"Default set to '{default}'. Run `cld <command>` to use it, "
                    f"or `cld -C {default} <command>` to select it explicitly.")
    elif unset_default:
        clear_default_config()
        logger.info("Default configuration cleared.")
    elif rm:
        if remove_config_keys(rm):
            logger.warning(f"Configuration '{rm}' not found.")
        else:
            if get_default_config_name() == rm:
                clear_default_config()
            logger.info(f"Configuration '{rm}' deleted.")
    elif ls:
        rows = list_configs()
        if as_json:
            print_json(rows)
        elif not rows:
            echo(NO_CONFIG_MESSAGE)
        else:
            echo(render_config_table(rows))
    elif show:
        curr_config = load_config()
        if show not in user_config_names(curr_config):
            raise BadParameter(f"Configuration {show} does not exist, use -ls to list available configurations.")

        config_obj = cloudinary.Config()
        # noinspection PyProtectedMember
        config_obj._setup_from_parsed_url(config_obj._parse_cloudinary_url(curr_config[show]))

        if as_json:
            return print_json(config_meta(show, curr_config, config_obj))

        _show_config_header(show, curr_config)
        return show_cloudinary_config(config_obj)
    else:
        if not is_valid_cloudinary_config():
            raise ConfigurationError("No Cloudinary configuration found.")
        if as_json:
            return print_json(active_config_meta(cloudinary.config()))
        _show_active_header()
        return show_cloudinary_config(cloudinary.config())


_REFRESH_MESSAGES = {
    "not_oauth": ("info", "'{name}' is an api-key config; nothing to refresh."),
    "fresh": ("info", "'{name}' token is still fresh; nothing to refresh (use --force to refresh anyway)."),
    "refreshed": ("info", "Refreshed '{name}'."),
    "failed": ("error", "'{name}' could not be refreshed; re-login with `{relogin}`."),
}


def _report_refresh(name, outcome):
    """Log the outcome of a single refresh. Returns True on success (or a benign no-op)."""
    level, template = _REFRESH_MESSAGES[outcome]
    # The re-login hint must carry the config's region so the right OAuth host is used.
    relogin = relogin_command(name) if outcome == "failed" else None
    getattr(logger, level)(template.format(name=name, relogin=relogin))
    return outcome != "failed"


def _refresh_one(name, force):
    name = name or active_config_name()
    if not name:
        raise UsageError("No active saved configuration to refresh; pass a name: "
                         "cld config --refresh <name>.")
    outcome = refresh_config(name, force=force)
    if outcome == "not_found":
        raise BadParameter(f"Configuration {name} does not exist, use -ls to list available configurations.")
    return _report_refresh(name, outcome)


def _refresh_all(force):
    results = refresh_configs(force=force)
    if not results:
        logger.info("No saved OAuth configurations to refresh.")
        return True
    ok = True
    for name, outcome in results.items():
        ok = _report_refresh(name, outcome) and ok
    return ok


def _show_config_header(name, cfg):
    flags = []
    if cfg.get(DEFAULT_CONFIG_KEY) == name:
        flags.append("default")
    if active_config_name() == name:
        flags.append("active")
    suffix = f" [{', '.join(flags)}]" if flags else ""
    echo(f"name: {name} ({config_type(cfg[name])}){suffix}\n")


def _show_active_header():
    """Header for bare `cld config`: identify the active config (saved name, -c URL, or env)."""
    name = active_config_name()
    if name is not None:
        _show_config_header(name, load_config())
        return
    active = cloudinary.config()
    type_label = config_type_label(active)
    label = SYNTHETIC_NAMES["url"] if active_config_is_url() else SYNTHETIC_NAMES["env"]
    echo(f"name: {label} ({type_label}) [active]\n")
