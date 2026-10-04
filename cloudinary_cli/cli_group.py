#!/usr/bin/env python3
import difflib
import platform
import shutil

import click
import click_log
import cloudinary

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_resolver import resolve_cli_config
from cloudinary_cli.version import __version__ as cli_version

CONTEXT_SETTINGS = dict(max_content_width=shutil.get_terminal_size()[0], terminal_width=shutil.get_terminal_size()[0])


class SuggestingGroup(click.Group):
    """Suggests similar command names when the command name is not known."""

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            names = [name for name in self.list_commands(ctx) if not self.get_command(ctx, name).hidden]
            matches = difflib.get_close_matches(args[0], names) if args else []
            if matches:
                e.message += f"\nDid you mean: {', '.join(matches)}?"
            raise


@click.group(cls=SuggestingGroup, context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
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
@click.pass_context
def cli(ctx, config, config_saved):
    subcommand = cli.get_command(ctx, ctx.invoked_subcommand) if ctx.invoked_subcommand else None
    warn_if_unconfigured = not getattr(subcommand, "config_optional", False)
    resolve_cli_config(config, config_saved, warn_if_unconfigured=warn_if_unconfigured)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)

    return True
