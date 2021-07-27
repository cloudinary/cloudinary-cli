#!/usr/bin/env python3
import sys

import click
import click_log
import cloudinary

import cloudinary_cli.core
import cloudinary_cli.modules
import cloudinary_cli.samples
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import initialize, load_config, refresh_cloudinary_config
from cloudinary_cli.utils.utils import log_exception

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config",
              help="""Tell the CLI which account to run the command on by specifying an account environment variable."""
              )
@click.option("-C", "--config_saved",
              help="""Tell the CLI which account to run the command on by specifying a saved configuration - see 
              `config` command.""")
@click_log.simple_verbosity_option(logger)
def cli(config, config_saved):
    if config:
        refresh_cloudinary_config(config)
    elif config_saved:
        config = load_config()
        if config_saved not in config:
            raise Exception(f"Config {config_saved} does not exist")

        refresh_cloudinary_config(config[config_saved])

    if cloudinary.config().cloud_name is None:
        logger.warning("No Cloudinary configuration found.")

    return 0


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
    initialize()
    try:
        exit_status = cli()
    except Exception as e:
        log_exception(e, "Command execution failed")
        exit_status = 1

    return exit_status


if __name__ == "__main__":
    sys.exit(main())
