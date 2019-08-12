from .admin import admin
from .config import config
from .search import search
from .uploader import uploader
from .utils import url
from .overrides import resolve_command
import click

setattr(click.MultiCommand, "resolve_command", resolve_command)
# print(click.Command)
