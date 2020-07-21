import click

from cloudinary_cli.core.admin import admin
from cloudinary_cli.core.config import config
from cloudinary_cli.core.search import search
from cloudinary_cli.core.uploader import uploader
from cloudinary_cli.core.provisioning import provisioning
from cloudinary_cli.core.utils import url, utils
from cloudinary_cli.core.overrides import resolve_command

setattr(click.MultiCommand, "resolve_command", resolve_command)

commands = [
    config,
    search,
    admin,
    uploader,
    provisioning,
    url,
    utils
]
