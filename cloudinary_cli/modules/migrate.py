from click import command, argument, option
from cloudinary import uploader as _uploader, api, Search
from cloudinary.utils import cloudinary_url as cld_url
from os import getcwd, walk, sep, remove, rmdir, listdir, mkdir
from os.path import dirname, splitext, split, join as path_join, abspath, isdir
from requests import get, head
from hashlib import md5
from itertools import product
from functools import reduce
from threading import Thread, active_count
from time import sleep
from ..utils import parse_option_value, log, F_OK, F_WARN, F_FAIL, load_template
from ..defaults import TEMPLATE_EXTS

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