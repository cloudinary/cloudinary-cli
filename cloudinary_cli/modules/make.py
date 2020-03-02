from click import command, argument

from cloudinary_cli.defaults import TEMPLATE_EXTS
from cloudinary_cli.utils import load_template, logger


@command("make", short_help="Scaffold Cloudinary templates.",
         help="""\b
Scaffold Cloudinary templates.
eg. cld make product gallery
""")
@argument("template", nargs=-1)
def make(template):
    language = "html"
    if template[-1] in TEMPLATE_EXTS.keys():
        language = template[-1]
        template = template[:-1]
    elif template[0] in TEMPLATE_EXTS.keys():
        language = template[0]
        template = template[1:]
    logger.info(load_template(language, '_'.join(template)))
