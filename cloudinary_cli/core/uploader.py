from click import command, argument, option
from cloudinary import uploader as upload_api

from cloudinary_cli.core.overrides import upload
from cloudinary_cli.utils.api_utils import handle_api_command

upload_api.upload = upload


@command("uploader",
         short_help="Run any methods that can be called through the upload API.",
         help="""
\b
Run any methods that can be called through the upload API.
Format: cld <cli options> uploader <command options> <method> <method parameters>
\te.g. cld uploader upload https://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
\b
\te.g. cld uploader rename flowers secret_flowers to_type=private
\t      OR
\t    cld uploader rename flowers secret_flowers -o to_type private
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-ls", "--ls", is_flag=True, help="List all available methods in the Upload API.")
@option("--save", nargs=1, help="Save output to a file.")
@option("-d", "--doc", is_flag=True, help="Open the Upload API reference in a browser.")
def uploader(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    return handle_api_command(params, optional_parameter, optional_parameter_parsed, ls, save, doc,
                              doc_url="https://cloudinary.com/documentation/image_upload_api_reference",
                              api_instance=upload_api,
                              api_name="upload")
