import os

from cloudinary_cli.version import __version__

# The SDK reads these variables on import and raises ValueError when one is invalid. Import it without them,
# then load each one again. An invalid one stays unset, so that -c/-C can still select a config.
# resolve_cli_config shows env_config_error when no -c/-C is given.
_env_urls = {name: os.environ.pop(name) for name in ("CLOUDINARY_URL", "CLOUDINARY_ACCOUNT_URL") if name in os.environ}

import cloudinary
import cloudinary.provisioning

env_config_error = None
for _name, _reset_config in (("CLOUDINARY_URL", cloudinary.reset_config),
                             ("CLOUDINARY_ACCOUNT_URL", cloudinary.provisioning.reset_config)):
    if _name not in _env_urls:
        continue
    os.environ[_name] = _env_urls[_name]
    try:
        _reset_config()
    except ValueError as e:
        del os.environ[_name]
        env_config_error = env_config_error or f"error: {e}. Fix or unset the {_name} environment variable."

cloudinary.USER_PLATFORM = f"CloudinaryCLI/{__version__}"
