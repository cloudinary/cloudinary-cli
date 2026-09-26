import sys

from cloudinary_cli.version import __version__

try:
    import cloudinary
except ValueError as e:
    # The SDK reads CLOUDINARY_URL on import, before the CLI can handle errors.
    sys.exit(f"error: {e}. Fix or unset the CLOUDINARY_URL environment variable.")

cloudinary.USER_PLATFORM = f"CloudinaryCLI/{__version__}"
