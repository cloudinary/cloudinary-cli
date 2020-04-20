from cloudinary_cli.version import __version__

import cloudinary

cloudinary.USER_PLATFORM = f"CloudinaryCLI/{__version__}"
