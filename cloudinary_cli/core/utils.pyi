from typing import List, Tuple, Any
from click import command, argument, option, Choice, echo, launch

@command("utils", help="Call Cloudinary utility methods.")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-ls", "--ls", is_flag=True, help="List all available utility methods.")
def utils(
    params: Tuple[str, ...],
    optional_parameter: List[Tuple[str, str]],
    optional_parameter_parsed: List[Tuple[str, str]],
    ls: bool
) -> bool:
    ...

@command("url", help="Generate a Cloudinary URL, which you can optionally open in your browser.")
@argument("public_id", required=True)
@argument("transformation", default="")
@option("-rt", "--resource_type", default="image", type=Choice(['image', 'video', 'raw']), help="The asset type")
@option("-t", "--type", "delivery_type", default="upload",
        type=Choice([
            'upload', 'private', 'public', 'authenticated', 'fetch', 'list', 'url2png',
            'sprite', 'text', 'multi', 'facebook', 'twitter', 'twitter_name', 'gravatar',
            'youtube', 'hulu', 'vimeo', 'animoto', 'worldstarhiphop', 'dailymotion'
        ]),
        help="The delivery type.")
@option("-o", "--open", 'open_in_browser', is_flag=True, help="Generate the derived asset and open it in your browser.")
@option("-s", "--sign", is_flag=True, help="Generate a signed URL.", default=False)
def url(
    public_id: str,
    transformation: str,
    resource_type: str,
    delivery_type: str,
    open_in_browser: bool,
    sign: bool
) -> None:
    ...
