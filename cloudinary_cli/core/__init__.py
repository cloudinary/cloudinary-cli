import click
import cloudinary.uploader

from cloudinary_cli.core.admin import admin
from cloudinary_cli.core.config import config
from cloudinary_cli.core.overrides import resolve_command, upload
from cloudinary_cli.core.search import search
from cloudinary_cli.core.uploader import uploader
from cloudinary_cli.core.utils import url

setattr(click.MultiCommand, "resolve_command", resolve_command)
cloudinary.uploader.upload = upload


def import_commands(cli):

    cli.add_command(config)
    cli.add_command(search)
    cli.add_command(admin)
    cli.add_command(uploader)
    cli.add_command(url)
