from unittest.mock import patch

import pytest
from filelock import FileLock

from cloudinary_cli.utils import config_utils


@pytest.fixture(autouse=True)
def isolate_cli_config(tmp_path):
    """Redirect the CLI config file to a fresh per-test path so the developer's real
    ~/.cloudinary-cli/config.json (saved accounts and __default__) never leaks into tests."""
    config_file = str(tmp_path / "config.json")
    with patch.object(config_utils, "CLOUDINARY_CLI_CONFIG_FILE", config_file), \
            patch.object(config_utils, "_config_lock", FileLock(config_file + ".lock")):
        yield
