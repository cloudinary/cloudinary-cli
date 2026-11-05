from click import command, argument, option
import cloudinary.collections

from cloudinary_cli.utils.api_utils import handle_api_command


@command("collections",
         short_help="Run any methods that can be called through the collections API.",
         help="""\b
Run any methods that can be called through the collections API.
Format: cld <cli options> collections <command options> <method> <method parameters>
\te.g. cld collections create_collection "Summer campaign" -o description "Campaign assets"
\t      OR
\t    cld collections add_collection_assets <collection_id> '["<asset_id>"]'
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2,
        help="Pass an optional parameter as a string, with no parsing. e.g. -o query summer")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass an optional parameter and parse its value as JSON or a boolean. "
             "e.g. -O configuration '{\"expression\": \"tags=summer\"}'")
@option("-ls", "--ls", is_flag=True, help="List all available methods in the Collections API.")
@option("--save", nargs=1, help="Save output to a file.")
@option("-d", "--doc", is_flag=True, help="Open the Collections API reference in a browser.")
def collections(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    return handle_api_command(params, optional_parameter, optional_parameter_parsed, ls, save, doc,
                              doc_url="https://cloudinary.com/documentation/collections_api",
                              api_instance=cloudinary.collections,
                              api_name="collections")
