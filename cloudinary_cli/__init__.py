from cloudinary_cli.version import __version__
from cloudinary_cli.utils.env_config import import_sdk

# Must run before any other `import cloudinary`, so that an invalid CLOUDINARY_URL does not stop the CLI.
import_sdk()

import cloudinary

cloudinary.USER_PLATFORM = f"CloudinaryCLI/{__version__}"
