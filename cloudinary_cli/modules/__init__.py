from .make import make
from .migrate import migrate
from .sync import sync
from .upload_dir import upload_dir
from .regenerate_all_derived_by_transformation import regenerate_all_derived_by_transformation

commands = [
    upload_dir,
    make,
    migrate,
    sync,
    regenerate_all_derived_by_transformation
]
