from sys import version_info

import cloudinary

__version__ = "0.4.0b"

cloudinary.USER_PLATFORM
cloudinary.USER_AGENT = "CloudinaryCLI/{} (Python {}, pycloudinary {})".format(
    __version__,
    ".".join(map(str, version_info[0:3])),
    cloudinary.VERSION)
