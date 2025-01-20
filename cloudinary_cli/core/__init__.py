import click

from cloudinary_cli.core.admin import admin
from cloudinary_cli.core.config import config
from cloudinary_cli.core.search import search, search_folders
from cloudinary_cli.core.uploader import uploader
from cloudinary_cli.core.provisioning import provisioning
from cloudinary_cli.core.utils import url, utils
from cloudinary_cli.core.overrides import resolve_command

setattr(click.MultiCommand, "resolve_command", resolve_command)

commands = [
    config,
    search,
    search_folders,
    admin,
    uploader,
    provisioning,
    url,
    utils
]
