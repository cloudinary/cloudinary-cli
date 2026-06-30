import click

from cloudinary_cli.core.admin import admin
from cloudinary_cli.core.auth import login, logout
from cloudinary_cli.core.config import config_command
from cloudinary_cli.core.search import search, search_folders
from cloudinary_cli.core.uploader import uploader
from cloudinary_cli.core.provisioning import provisioning
from cloudinary_cli.core.utils import url, utils
from cloudinary_cli.core.overrides import resolve_command

setattr(click.Group, "resolve_command", resolve_command)

commands = [
    config_command,
    login,
    logout,
    search,
    search_folders,
    admin,
    uploader,
    provisioning,
    url,
    utils
]
