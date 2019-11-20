#!/usr/bin/env python3
from json import loads

import click
import cloudinary
import cloudinary_cli.core
import cloudinary_cli.modules
import cloudinary_cli.samples

from .defaults import CLOUDINARY_CLI_CONFIG_FILE

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""Temporary configuration to use. To use permanent config:
echo \"export CLOUDINARY_URL=YOUR_CLOUDINARY_URL\" >> ~/.bash_profile && source ~/.bash_profile
""")
@click.option("-C", "--config_saved", help="""Saved configuration to use - see `config` command""")
def cli(config, config_saved):
    if config:
        cloudinary._config._parse_cloudinary_url(config)
    elif config_saved:
        cloudinary._config._parse_cloudinary_url(loads(open(CLOUDINARY_CLI_CONFIG_FILE).read())[config_saved])
    pass


cloudinary_cli.core.import_commands(cli)
cloudinary_cli.modules.import_commands(cli)
cloudinary_cli.samples.import_commands(cli)


def main():
    cli()
