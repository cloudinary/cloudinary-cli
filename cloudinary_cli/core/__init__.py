from .admin import admin
from .config import config
from .search import search
from .uploader import uploader
from .utils import url
from .overrides import resolve_command, upload
import click

setattr(click.MultiCommand, "resolve_command", resolve_command)
# print(click.Command)

import cloudinary.uploader
cloudinary.uploader.upload = upload