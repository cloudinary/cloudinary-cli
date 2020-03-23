from .make import make
from .migrate import migrate
from .sync import sync
from .upload_dir import upload_dir
from .find_empty_folders import find_empty_folders

def import_commands(cli):

    cli.add_command(upload_dir)
    cli.add_command(make)
    cli.add_command(migrate)
    cli.add_command(sync)
    cli.add_command(find_empty_folders)
