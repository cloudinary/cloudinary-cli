import os

from click import argument, echo, option

from cloudinary_cli.cli_group import cli
from cloudinary_cli.defaults import TEMPLATE_EXTS, TEMPLATE_FOLDER
from cloudinary_cli.utils.utils import load_template, print_help_and_exit


@cli.command("make", short_help="Return template code for implementing the specified Cloudinary widget.",
             help="""\b
Return template code for implementing the specified Cloudinary widget.
e.g. cld make media library widget
     cld make python find all empty folders
""")
@argument("template", nargs=-1)
@option("-ll", "--list-languages", is_flag=True, help="List available languages.")
@option("-lt", "--list-templates", is_flag=True, help="List available templates.")
def make(template, list_languages, list_templates):
    if not any([template, list_languages, list_templates]):
        print_help_and_exit()

    if list_languages:
        echo("Available languages")
        with os.scandir(TEMPLATE_FOLDER) as languages:
            for tpl_language in languages:
                if tpl_language.is_dir():
                    echo(tpl_language.name)
        return True

    language, template = _handle_language_and_template(template)

    if list_templates:
        echo(f"Available templates for language: {language}")
        with os.scandir(os.path.join(TEMPLATE_FOLDER, language)) as templates:
            for template_file in templates:
                if template_file.is_file():
                    echo(template_file.name.replace("_", " "))
        return True

    template_result = load_template(language, '_'.join(template))

    if not template_result:
        return False

    echo(template_result)

    return True


def _handle_language_and_template(language_and_template):
    language = "html"  # default language, in case not specified

    if not language_and_template:
        return language, language_and_template

    template = list(language_and_template)
    if template[-1] in TEMPLATE_EXTS.keys():
        language = template.pop()
    elif template[0] in TEMPLATE_EXTS.keys():
        language = template.pop(0)

    return language, template
