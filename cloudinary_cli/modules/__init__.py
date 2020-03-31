from .make import make
from .migrate import migrate
from .sync import sync
from .upload_dir import upload_dir

commands = [
    upload_dir,
    make,
    migrate,
    sync,
]
