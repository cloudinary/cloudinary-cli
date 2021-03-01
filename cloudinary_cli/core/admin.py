from click import command, argument, option
from cloudinary import api

from cloudinary_cli.utils.api_utils import handle_api_command


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
def admin(params, optional_parameter, optional_parameter_parsed,
          auto_paginate, force, filter_fields,
          ls, save, doc):
    return handle_api_command(params, optional_parameter, optional_parameter_parsed,
                              ls, save, doc,
                              doc_url="https://cloudinary.com/documentation/admin_api",
                              api_instance=api,
                              api_name="admin",
                              auto_paginate=auto_paginate,
                              force=force,
                              filter_fields=filter_fields)
