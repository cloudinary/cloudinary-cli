import logging
import os
from os.path import join as path_join, expanduser, abspath, dirname

import click_log

logger = logging.getLogger(__name__)

click_log.basic_config(logger)

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

TEMPLATE_FOLDER_NAME = 'templates'
CLOUDINARY_CLI_ROOT = dirname(__file__)
TEMPLATE_FOLDER = path_join(CLOUDINARY_CLI_ROOT, TEMPLATE_FOLDER_NAME)
CUSTOM_TEMPLATE_FOLDER = path_join(abspath(CLOUDINARY_HOME), TEMPLATE_FOLDER_NAME)

OLD_CLOUDINARY_CLI_CONFIG_FILE = path_join(expanduser("~"), '.cloudinary-cli-config')
