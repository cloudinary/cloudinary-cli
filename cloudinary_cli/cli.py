#!/usr/bin/env python3
import sys

from click import ClickException

import cloudinary_cli.core
import cloudinary_cli.modules
import cloudinary_cli.samples
from cloudinary_cli.cli_group import cli
from cloudinary_cli.utils.config_utils import initialize
from cloudinary_cli.utils.utils import log_exception, ConfigurationError


def import_commands(*command_modules):
    for command_module in command_modules:
        for command in command_module:
            cli.add_command(command)


import_commands(
    cloudinary_cli.core.commands,
    cloudinary_cli.modules.commands,
    cloudinary_cli.samples.commands,
)


def main():
    exit_status = 1  # very optimistic :)

    initialize()

    try:
        # we don't use standalone mode to get the return value from the command execution
        exit_status = cli.main(standalone_mode=False)
    except ClickException as e:
        # show usage with error message
        e.show()
    except ConfigurationError as e:
        log_exception(e)
    except Exception as e:
        # Improve configuration error handling
        if "Must supply cloud_name" in str(e):
            log_exception("No Cloudinary configuration found.")
        else:
            log_exception(e, "Command execution failed")

    if type(exit_status) == int:
        return exit_status

    return 0 if exit_status or exit_status is None else 1


if __name__ == "__main__":
    sys.exit(main())
