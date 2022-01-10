from click import command, argument, option, Choice, echo, launch
from cloudinary import utils as cld_utils

from cloudinary_cli.core.overrides import cloudinary_url
from cloudinary_cli.utils.api_utils import handle_command
from cloudinary_cli.utils.utils import print_api_help

cld_utils.cloudinary_url = cloudinary_url

utils_list = ["api_sign_request", "cloudinary_url", "download_archive_url", "download_zip_url", "private_download_url",
              "download_folder", "download_backedup_asset", "verify_api_response_signature",
              "verify_notification_signature"]


@command("utils", help="Call Cloudinary utility methods.")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-ls", "--ls", is_flag=True, help="List all available utility methods.")
def utils(params, optional_parameter, optional_parameter_parsed, ls):
    if ls or len(params) < 1:
        return print_api_help(cld_utils, allow_list=utils_list)

    res = handle_command(params, optional_parameter, optional_parameter_parsed, cld_utils, "Utils")
    if not res:
        return False

    echo(res)

    return True


@command("url", help="Generate a Cloudinary URL, which you can optionally open in your browser.")
@argument("public_id", required=True)
@argument("transformation", default="")
@option("-rt", "--resource_type", default="image", type=Choice(['image', 'video', 'raw']), help="The asset type")
@option("-t", "--type", "delivery_type", default="upload",
        type=Choice(['upload', 'private', 'authenticated', 'fetch', 'list', 'url2png']),
        help="The delivery type.")
@option("-o", "--open", 'open_in_browser', is_flag=True, help="Generate the derived asset and open it in your browser.")
@option("-s", "--sign", is_flag=True, help="Generate a signed URL.", default=False)
def url(public_id, transformation, resource_type, delivery_type, open_in_browser, sign):
    if delivery_type == "authenticated" or resource_type == "url2png":
        sign = True
    elif delivery_type == "list":
        public_id += ".json"

    res = cloudinary_url(public_id, resource_type=resource_type,
                         raw_transformation=transformation, type=delivery_type, sign_url=sign)
    echo(res)

    if open_in_browser:
        launch(res)
