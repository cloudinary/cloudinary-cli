from click import command, argument, option, echo

from cloudinary_cli.auth import login as run_login, logout as run_logout, list_oauth_login_names
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import log_exception, prompt_user


@command("login", help="Log in to Cloudinary via OAuth (opens a browser). The session is saved "
                       "as a named configuration you can select with `-C`.")
@argument("name", required=False)
@option("--region",
        help="Cloudinary region to log in to (e.g. eu, ap, or api-eu). Defaults to the "
             "global region (api).")
@option("--set-default", "set_default", is_flag=True,
        help="Set this login as the default configuration used when no -c/-C and no environment "
             "config is given.")
def login(name, region, set_default):
    try:
        config_name, is_default = run_login(region=region, name=name, set_default=set_default)
    except Exception as e:
        log_exception(e, "Login failed")
        return False

    logger.info(f"Logged in. Saved as '{config_name}'.")
    if is_default:
        logger.info(f"This is now the default configuration. Run `cld <command>` to use it, "
                    f"or `cld -C {config_name} <command>` to select it explicitly.")
    else:
        logger.info(f"Run `cld -C {config_name} <command>` to use it, "
                    f"or make it the default with `cld config -d {config_name}`.")
    return True


@command("logout", help="Log out: revoke a saved OAuth login's token and remove its configuration. "
                        "Run without a name to choose from the saved logins.")
@argument("name", required=False)
def logout(name):
    if not name:
        action, name = _select_oauth_login()
        if action == "invalid":
            return False
        if action != "selected":
            return True

    status = run_logout(name)
    if status == "removed":
        logger.info(f"Logged out of '{name}'. Its token was revoked and the saved login removed.")
    elif status == "revoke_failed":
        logger.warning(f"Removed '{name}', but could not revoke its token at the server "
                       f"(it may still be valid until it expires).")
    elif status == "not_oauth":
        logger.error(f"'{name}' is not an OAuth login; refusing to remove it. "
                     f"Use `config -rm {name}` to delete a saved configuration.")
        return False
    else:
        logger.info(f"No saved OAuth configuration named '{name}'.")
    return True


def _select_oauth_login():
    """
    Prompt the user to pick a saved OAuth login by number.

    Returns ("selected", name), ("cancelled", None), ("none", None), or ("invalid", None).
    """
    names = list_oauth_login_names()
    if not names:
        logger.info("No saved OAuth logins to log out of.")
        return "none", None

    echo("Saved OAuth logins:")
    for i, name in enumerate(names, start=1):
        echo(f"  {i}) {name}")

    # The selection needs real input that no flag replaces, so on non-interactive stdin prompt_user
    # returns None (after logging the hint) and we report it as an invalid (non-zero) outcome.
    choice = prompt_user(
        f"Select a login to log out of [1-{len(names)}] (or Enter to cancel): ",
        noninteractive_hint="Pass the configuration name directly: `cld logout <name>`.")
    if choice is None:
        return "invalid", None
    choice = choice.strip()
    if not choice:
        return "cancelled", None
    if not (choice.isdigit() and 1 <= int(choice) <= len(names)):
        logger.error(f"Invalid selection '{choice}'. Expected a number between 1 and {len(names)}.")
        return "invalid", None
    return "selected", names[int(choice) - 1]
