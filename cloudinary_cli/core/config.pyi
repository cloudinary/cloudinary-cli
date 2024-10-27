from typing import Optional, Any, Tuple
from click import command, option

@command("config", help="Display the current configuration, and manage additional configurations.")
@option("-n", "--new", help="""\b Create and name a configuration from a Cloudinary account environment variable.
e.g. cld config -n <NAME> <CLOUDINARY_URL>""", nargs=2)
@option("-ls", "--ls", help="List all saved configurations.", is_flag=True)
@option("-s", "--show", help="Show details of a specified configuration.", nargs=1)
@option("-rm", "--rm", help="Delete a specified configuration.", nargs=1)
@option("-url", "--from_url",
        help="Create a configuration from a Cloudinary account environment variable. "
             "The configuration name is the cloud name.",
        nargs=1)
def config(
    new: Optional[Tuple[str, str]],
    ls: bool,
    show: Optional[str],
    rm: Optional[str],
    from_url: Optional[str]
) -> Optional[Any]:
    ...
