from typing import List, Tuple, Any, Optional
from click import command, argument, option

@command("provisioning",
         short_help="Run any methods that can be called through the provisioning API.",
         help="""\b
Run any methods that can be called through the provisioning API.
Format: cld <cli options> provisioning <command options> <method> <method parameters>
\te.g. cld provisioning sub_accounts
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-ls", "--ls", is_flag=True, help="List all available methods in the Provisioning API.")
@option("--save", nargs=1, help="Save output to a file.")
@option("-d", "--doc", is_flag=True, help="Open the Provisioning API reference in a browser.")
def provisioning(
    params: Tuple[str, ...],
    optional_parameter: List[Tuple[str, str]],
    optional_parameter_parsed: List[Tuple[str, str]],
    ls: bool,
    save: Optional[str],
    doc: bool
) -> Any:
    ...
