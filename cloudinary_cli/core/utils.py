from cloudinary_cli.utils import *
from webbrowser import open as open_url
from csv import DictWriter
from cloudinary.utils import cloudinary_url as cld_url
from cloudinary import api, uploader as _uploader
from click import command, argument, option, Choice

@command("url", help="Generate a cloudinary url")
@argument("public_id", required=True)
@argument("transformation", default="")
@option("-rt", "--resource_type", default="image", type=Choice(['image', 'video', 'raw']), help="Resource Type")
@option("-t", "--type", default="upload", type=Choice(['upload', 'private', 'authenticated', 'fetch', 'list', 'url2png']), help="Type of the resource")
@option("-o", "--open", is_flag=True, help="Open URL in your browser")
@option("-s", "--sign", is_flag=True, help="Generates a signed URL", default=False)
def url(public_id, transformation, resource_type, type, open, sign):
    if type == "authenticated" or resource_type == "url2png":
        sign = True
    elif type == "list":
        public_id += ".json"
    res = cld_url(public_id, resource_type=resource_type, raw_transformation=transformation, type=type, sign_url=sign)[0]
    print(res)
    if open:
        open_url(res)
