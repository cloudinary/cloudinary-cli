import os
from typing import List
from click import command, argument, option

@command("migrate",
         short_help="Migrate files using an existing auto-upload mapping and a file of URLs.",
         help="Migrate a list of external media files to Cloudinary. "
              "The URLs of the files to migrate are listed in a separate file and must all have the same prefix.")
@argument("upload_mapping", type=str)
@argument("file", type=str)
@option("-d", "--delimiter", default="\n", help="The separator used between the URLs. Default: New line")
@option("-v", "--verbose", is_flag=True)
def migrate(
    upload_mapping: str,
    file: str,
    delimiter: str,
    verbose: bool
) -> bool:
    ...

