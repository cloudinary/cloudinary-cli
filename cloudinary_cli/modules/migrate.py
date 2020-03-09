from os.path import join

from click import command, argument, option
from cloudinary import api
from cloudinary.utils import cloudinary_url
from requests import head

from cloudinary_cli.utils import logger


@command("migrate",
         short_help="Migrate files using an existing auto-upload mapping and a file of URLs.",
         help="Migrate a list of external media files to Cloudinary. The URLs of the files to migrate are listed in a separate file and must all have the same prefix.")
@argument("upload_mapping")
@argument("file")
@option("-d", "--delimiter", default="\n", help="The separator used between the URLs. Default: New line")
@option("-v", "--verbose", is_flag=True)
def migrate(upload_mapping, file, delimiter, verbose):
    with open(file) as f:
        items = f.read().split(delimiter)
    mapping = api.upload_mapping(upload_mapping)
    items = map(lambda x: cloudinary_url(join(mapping['folder'], x[len(mapping['template']):])),
                filter(lambda x: x != '', items))
    for i in items:
        res = head(i[0])
        if res.status_code != 200:
            logger.error("Failed uploading asset: " + res.__dict__['headers']['X-Cld-Error'])
        elif verbose:
            logger.info("Uploaded {}".format(i[0]))
