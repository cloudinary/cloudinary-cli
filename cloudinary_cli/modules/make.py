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

@command("make", short_help="Scaffold Cloudinary templates.",
         help="""\b
Scaffold Cloudinary templates.
eg. cld make product gallery
""")
@argument("template", nargs=-1)
def make(template):
    language = "html"
    if template[-1] in TEMPLATE_EXTS.keys():
        language = template[-1]
        template = template[:-1]
    elif template[0] in TEMPLATE_EXTS.keys():
        language = template[0]
        template = template[1:]
    print(load_template(language, '_'.join(template)))
