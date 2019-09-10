from .admin import admin
from .config import config
from .search import search
from .uploader import uploader
from .provisioning import provisioning
from .utils import url
import cloudinary.uploader
from .overrides import resolve_command, upload
import click

setattr(click.MultiCommand, "resolve_command", resolve_command)
cloudinary.uploader.upload = upload
