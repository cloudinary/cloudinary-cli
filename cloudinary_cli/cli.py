#!/usr/bin/env python3
from json import loads
import os
import click
import cloudinary
import cloudinary_cli.core
import cloudinary_cli.modules
import cloudinary_cli.samples
import click_log

from .defaults import CLOUDINARY_CLI_CONFIG_FILE
from cloudinary_cli.utils import logger, initialize

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""Temporary configuration to use. To use environment config:
echo \"export CLOUDINARY_URL=YOUR_CLOUDINARY_URL\" >> ~/.bash_profile && source ~/.bash_profile
""")
@click.option("-C", "--config_saved", help="""Saved configuration to use - see `config` command""")
@click_log.simple_verbosity_option(logger)
def cli(config, config_saved):
    if config:
        os.environ.update(dict(CLOUDINARY_URL=config))
    elif config_saved:
        os.environ.update(dict(CLOUDINARY_URL=loads(open(CLOUDINARY_CLI_CONFIG_FILE).read())[config_saved]))
    cloudinary.reset_config()
    if cloudinary.config().cloud_name is None:
        logger.warning("CLOUDINARY_URL is not configured in your environment.")
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
