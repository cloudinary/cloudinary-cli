from .make import make
from .migrate import migrate
from .sync import sync
from .upload_dir import upload_dir
from .regen_derived import regen_derived
from .copy import copy

commands = [
    upload_dir,
    make,
    migrate,
    sync,
    regen_derived,
    copy
]
