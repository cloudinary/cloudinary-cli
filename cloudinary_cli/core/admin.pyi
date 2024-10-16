from typing import List, Tuple, Any
from click import command, argument, option

@command("admin",
         short_help="Run any methods that can be called through the admin API.",
         help="""\b
Run any methods that can be called through the admin API.
Format: cld <cli options> admin <command options> <method> <method parameters>
\te.g. cld admin resources max_results=10 tags=sample
\t      OR
\t    cld admin resources -o max_results 10 -o tags sample
\t      OR
\t    cld admin resources max_results=10 -o tags sample
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-A", "--auto_paginate", is_flag=True, help="Will auto paginate Admin API calls.", default=False)
@option("-ff", "--filter_fields", multiple=True, help="Filter fields to return when using auto pagination.")
@option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate.")
@option("-ls", "--ls", is_flag=True, help="List all available methods in the Admin API.")
@option("--save", nargs=1, help="Save output to a file.")
@option("-d", "--doc", is_flag=True, help="Open the Admin API reference in a browser.")
def admin(
    params: Tuple[str, ...],
    optional_parameter: List[Tuple[str, str]],
    optional_parameter_parsed: List[Tuple[str, str]],
    auto_paginate: bool,
    force: bool,
    filter_fields: List[str],
    ls: bool,
    save: str,
    doc: bool
) -> Any:
    ...
