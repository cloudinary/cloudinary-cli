from os.path import join as path_join

from click import command, argument, option
from cloudinary import api
from cloudinary.utils import cloudinary_url as cld_url
from requests import head

from ..utils import F_OK, F_FAIL


@command("migrate",
         short_help="Migrate files using an existing auto-upload mapping and a file of URLs",
         help="Migrate files using an existing auto-upload mapping and a file of URLs")
@argument("upload_mapping")
@argument("file")
@option("-d", "--delimiter", default="\n", help="Separator for the URLs. Default: New line")
@option("-v", "--verbose", is_flag=True)
def migrate(upload_mapping, file, delimiter, verbose):
    with open(file) as f:
        items = f.read().split(delimiter)
    mapping = api.upload_mapping(upload_mapping)
    items = map(lambda x: cld_url(path_join(mapping['folder'], x[len(mapping['template']):])),
                filter(lambda x: x != '', items))
    for i in items:
        res = head(i[0])
        if res.status_code != 200:
            print(F_FAIL("Failed uploading asset: " + res.__dict__['headers']['X-Cld-Error']))
        elif verbose:
            print(F_OK("Uploaded {}".format(i[0])))
