from click import command, argument, option
import cloudinary.provisioning

from cloudinary_cli.utils.api_utils import handle_api_command


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
def provisioning(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    return handle_api_command(params, optional_parameter, optional_parameter_parsed, ls, save, doc,
                              doc_url="https://cloudinary.com/documentation/provisioning_api",
                              api_instance=cloudinary.provisioning,
                              api_name="provisioning")
