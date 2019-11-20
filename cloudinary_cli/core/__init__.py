import click
import cloudinary.uploader

from .admin import admin
from .config import config
from .overrides import resolve_command, upload
from .search import search
from .uploader import uploader
from .utils import url

setattr(click.MultiCommand, "resolve_command", resolve_command)
cloudinary.uploader.upload = upload


def import_commands(cli):

    cli.add_command(config)
    cli.add_command(search)
    cli.add_command(admin)
    cli.add_command(uploader)
    cli.add_command(url)
