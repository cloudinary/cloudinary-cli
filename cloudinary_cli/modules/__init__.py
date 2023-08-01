from .make import make
from .migrate import migrate
from .sync import sync
from .upload_dir import upload_dir
from .delete_all_derived_by_transformation import delete_all_derived_by_transformation

commands = [
    upload_dir,
    make,
    migrate,
    sync,
    delete_all_derived_by_transformation
]
