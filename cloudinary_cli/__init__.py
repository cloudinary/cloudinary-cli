import cloudinary
from sys import version_info

VERSION = "0.3.0"

cloudinary.USER_AGENT = "CloudinaryCLI/{} (Python {}, pycloudinary {})".format(
    VERSION,
    ".".join(map(str, version_info[0:3])),
    cloudinary.VERSION)
