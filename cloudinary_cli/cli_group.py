#!/usr/bin/env python3
import platform
import shutil

import click
import click_log
import cloudinary

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import load_config, refresh_cloudinary_config, \
    is_valid_cloudinary_config
from cloudinary_cli.version import __version__ as cli_version

CONTEXT_SETTINGS = dict(max_content_width=shutil.get_terminal_size()[0], terminal_width=shutil.get_terminal_size()[0])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.help_option()
@click.version_option(cli_version, prog_name="Cloudinary CLI",
                      message=f"%(prog)s, version %(version)s\n"
                              f"Cloudinary SDK, version {cloudinary.VERSION}\n"
                              f"Python, version {platform.python_version()}")
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

    if not is_valid_cloudinary_config():
        logger.warning("No Cloudinary configuration found.")

    return True
