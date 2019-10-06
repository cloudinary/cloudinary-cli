from sys import version_info

import cloudinary

VERSION = "0.3.1"

cloudinary.USER_AGENT = "CloudinaryCLI/{} (Python {}, pycloudinary {})".format(VERSION,
                                                                               ".".join(map(str, version_info[0:3])),
                                                                               cloudinary.VERSION)
