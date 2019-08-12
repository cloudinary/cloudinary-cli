# from ..utils import *
from webbrowser import open as open_url
from csv import DictWriter
from cloudinary import api, uploader

import click
from click import Command
from click.utils import make_str
from click.parser import split_opt

def resolve_command(self, ctx, args):
    cmd_name = make_str(args[0])
    original_cmd_name = cmd_name

    # Get the command
    cmd = self.get_command(ctx, cmd_name)

    # If we can't find the command but there is a normalization
    # function available, we try with that one.
    if cmd is None and ctx.token_normalize_func is not None:
        cmd_name = ctx.token_normalize_func(cmd_name)
        cmd = self.get_command(ctx, cmd_name)

    # If we don't find the command we want to show an error message
    # to the user that it was not provided.  However, there is
    # something else we should do: if the first argument looks like
    # an option we want to kick off parsing again for arguments to
    # resolve things like --help which now should go to the main
    # place.
    if cmd is None and not ctx.resilient_parsing:
        if split_opt(cmd_name)[0]:
            self.parse_args(ctx, ctx.args)

        if original_cmd_name in api.__dict__:
            cmd = self.get_command(ctx, "admin")
            return cmd_name, cmd, args
        elif original_cmd_name in uploader.__dict__:
            cmd = self.get_command(ctx, "uploader")
            return cmd_name, cmd, args
        else:
            ctx.fail('No such command "%s".' % original_cmd_name)

    return cmd_name, cmd, args[1:]
