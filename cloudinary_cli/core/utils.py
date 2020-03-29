from webbrowser import open as open_url

from click import command, argument, option, Choice, echo
from cloudinary.utils import cloudinary_url


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
                         raw_transformation=transformation, type=type, sign_url=sign)[0]
    echo(res)

    if open_in_browser:
        open_url(res)
