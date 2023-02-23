import os

from click import command, argument, option
from cloudinary import api
from cloudinary.exceptions import Error
from cloudinary.utils import cloudinary_url
from requests import head

from cloudinary_cli.utils.utils import logger, log_exception


@command("migrate",
         short_help="Migrate files using an existing auto-upload mapping and a file of URLs.",
         help="Migrate a list of external media files to Cloudinary. "
              "The URLs of the files to migrate are listed in a separate file and must all have the same prefix.")
@argument("upload_mapping")
@argument("file")
@option("-d", "--delimiter", default="\n", help="The separator used between the URLs. Default: New line")
@option("-v", "--verbose", is_flag=True)
def migrate(upload_mapping, file, delimiter, verbose):
    if not os.path.exists(file):
        logger.error(f"Migration file: '{file}' does not exist")
        return False

    try:
        with open(file) as f:
            migration_files = f.read().split(delimiter)
    except IOError as e:
        log_exception(e, f"Failed reading migration file: '{file}'")
        return False

    try:
        mapping = api.upload_mapping(upload_mapping)
    except Error as e:
        log_exception(e, f"Failed retrieving upload mapping: '{upload_mapping}'")
        return False

    exit_status = True
    migration_urls = []

    for migration_file in filter(None, migration_files):  # omit empty lines
        if not migration_file.startswith(mapping['template']):
            logger.error(f"Skipping '{migration_file}', it does not belong to the upload mapping")
            exit_status = False
            continue

        migration_urls.append(cloudinary_url('/'.join([mapping['folder'], migration_file[len(mapping['template']):]])))

    for migration_url in migration_urls:
        res = head(migration_url)
        if res.status_code != 200:
            logger.error(f"Failed uploading {migration_url}: {res.__dict__['headers']['X-Cld-Error']}")
        elif verbose:
            logger.info(f"Uploaded {migration_url}")

    return exit_status
