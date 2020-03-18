#!/usr/bin/env python3
import json
import os
import click
import cloudinary
import cloudinary_cli.core
import cloudinary_cli.modules
import cloudinary_cli.samples
import click_log

from cloudinary_cli.defaults import CLOUDINARY_CLI_CONFIG_FILE
from cloudinary_cli.utils import logger, initialize

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""Tell the CLI which account to run the command on by specifying an account environment variable. 
""")
@click.option("-C", "--config_saved", help="""Tell the CLI which account to run the command on by specifying a saved configuration - see `config` command.""")
@click_log.simple_verbosity_option(logger)
def cli(config, config_saved):
    if config:
        os.environ.update(dict(CLOUDINARY_URL=config))
    elif config_saved:
        with open(CLOUDINARY_CLI_CONFIG_FILE) as f:
            os.environ.update(dict(CLOUDINARY_URL=json.loads(f.read())[config_saved]))
    cloudinary.reset_config()
    if cloudinary.config().cloud_name is None:
        logger.warning("No Cloudinary configuration found.")
    pass


cloudinary_cli.core.import_commands(cli)
cloudinary_cli.modules.import_commands(cli)
cloudinary_cli.samples.import_commands(cli)


def main():
    initialize()
    try:
        cli()
    except Exception as e:
        logger.error(str(e))
