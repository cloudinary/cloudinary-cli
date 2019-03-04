VERSION = "0.2.2-beta"

import cloudinary
from sys import version_info

cloudinary.USER_AGENT = "CloudinaryCLI/{} (Python {})".format(VERSION, ".".join(map(str, version_info[0:3])))