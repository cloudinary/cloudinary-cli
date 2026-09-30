#!/usr/bin/env python3
# Do not import the SDK at the top: import_sdk must run before the first `import cloudinary`.
import os

_ENV_VARS = ("CLOUDINARY_URL", "CLOUDINARY_ACCOUNT_URL")
_errors = {}


def import_sdk():
    """
    Import the SDK so that an invalid CLOUDINARY_URL or CLOUDINARY_ACCOUNT_URL does not stop the CLI.

    The SDK loads these variables on import and raises when one is invalid, so they are held back during
    the import. Then each config class loads the environment through a safe wrapper: a failed load leaves
    an empty config and records the error, which env_config_error returns when the variable is needed.
    """
    held = {name: os.environ.pop(name) for name in _ENV_VARS if name in os.environ}
    try:
        import cloudinary
        import cloudinary.provisioning
    finally:
        os.environ.update(held)

    _wrap_load_from_env(cloudinary.Config, "CLOUDINARY_URL")
    _wrap_load_from_env(cloudinary.provisioning.AccountConfig, "CLOUDINARY_ACCOUNT_URL")
    cloudinary.reset_config()
    cloudinary.provisioning.reset_config()


def env_config_error(name):
    """The error message for an invalid environment variable `name`, or None if it loaded."""
    return _errors.get(name)


def _wrap_load_from_env(config_class, name):
    load_from_env = config_class._load_config_from_env

    def safe_load_from_env(self):
        before = dict(self.__dict__)
        try:
            load_from_env(self)
        except (ValueError, TypeError) as e:
            # Do not keep the values that loaded before the error.
            self.__dict__.clear()
            self.__dict__.update(before)
            _errors[name] = f"error: {e}. Fix or unset the {name} environment variable."

    config_class._load_config_from_env = safe_load_from_env
