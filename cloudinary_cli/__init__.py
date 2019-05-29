VERSION = "0.2.4.1"

import cloudinary
from sys import version_info

cloudinary.USER_AGENT = "CloudinaryCLI/{} (Python {}, pycloudinary {})".format(VERSION, ".".join(map(str, version_info[0:3])), cloudinary.VERSION)