import os
from typing import Tuple, List, Optional
from click import argument, echo, option
from cloudinary_cli.cli_group import cli

@cli.command("make", short_help="Return template code for implementing the specified Cloudinary widget.",
             help="""\b
Return template code for implementing the specified Cloudinary widget.
e.g. cld make media library widget
     cld make python find all empty folders
""")
@argument("template", nargs=-1)
@option("-ll", "--list-languages", is_flag=True, help="List available languages.")
@option("-lt", "--list-templates", is_flag=True, help="List available templates.")
def make(
    template: Tuple[str, ...],
    list_languages: bool,
    list_templates: bool
) -> bool:
    ...

def _handle_language_and_template(language_and_template: Tuple[str, ...]) -> Tuple[str, List[str]]:
    ...
