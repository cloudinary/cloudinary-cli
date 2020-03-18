from click import command, argument

from cloudinary_cli.defaults import TEMPLATE_EXTS, logger
from cloudinary_cli.utils import load_template


@command("make", short_help="Return template code for implementing the specified Cloudinary widget.",
         help="""\b
Return template code for implementing the specified Cloudinary widget.
e.g. cld make product_gallery
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
    try:
        src = load_template(language, '_'.join(template))
        print(src)
    except Exception as e:
        logger.error(e)
