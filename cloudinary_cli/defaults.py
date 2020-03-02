import logging
import os
from os.path import join as path_join, expanduser, abspath

import click_log

TEMPLATE_FOLDER = "templates"

TEMPLATE_EXTS = {
    "python": "py",
    "html": "html",
    "ruby": "rb",
    "node": "js",
    "php": "php",
    "java": "java",
}

CLOUDINARY_HOME = os.environ.get('CLOUDINARY_HOME')

if CLOUDINARY_HOME is None:
    CLOUDINARY_HOME = abspath(path_join(expanduser("~"), ".cloudinary-cli"))

CLOUDINARY_CLI_CONFIG_FILE = abspath(path_join(CLOUDINARY_HOME, 'config.json'))
CUSTOM_TEMPLATE_FOLDER = abspath(path_join(CLOUDINARY_HOME, 'templates'))

OLD_CLOUDINARY_CLI_CONFIG_FILE = abspath(path_join(expanduser("~"), '.cloudinary-cli-config'))

logger = logging.getLogger(__name__)

click_log.basic_config(logger)
