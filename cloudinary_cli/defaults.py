from os.path import join as path_join, expanduser, abspath, isdir, exists
from os import mkdir

TEMPLATE_FOLDER = "templates"

TEMPLATE_EXTS = {
    "python": "py",
    "html": "html",
    "ruby": "rb",
    "node": "js",
    "php": "php",
    "java": "java",
}

CLOUDINARY_CLI_CONFIG_FILE = abspath(path_join(expanduser("~"), '.cloudinary-cli-config'))

if not exists(CLOUDINARY_CLI_CONFIG_FILE):
    open(CLOUDINARY_CLI_CONFIG_FILE, "a").close()

CUSTOM_TEMPLATE_FOLDER = abspath(path_join(expanduser("~"), '.cld-cli-templates'))

if not isdir(CUSTOM_TEMPLATE_FOLDER):
    mkdir(CUSTOM_TEMPLATE_FOLDER)