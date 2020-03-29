import cloudinary
from click import command, option, echo

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import load_config, verify_cloudinary_url, update_config, remove_config_keys


@command("config", help="Display the current configuration, and manage additional configurations.")
@option("-n", "--new", help="""\b Create and name a configuration from a Cloudinary account environment variable.
e.g. cld config -n <NAME> <CLOUDINARY_URL>""", nargs=2)
@option("-ls", "--ls", help="List all saved configurations.", is_flag=True)
@option("-rm", "--rm", help="Delete a specified configuration.", nargs=1)
@option("-url", "--from_url",
        help="Create a configuration from a Cloudinary account environment variable. "
             "The configuration name is the cloud name.",
        nargs=1)
def config(new, ls, rm, from_url):
    if new or from_url:
        config_name, cloudinary_url = new or [None, from_url]

        if not verify_cloudinary_url(cloudinary_url):
            return

        config_name = config_name or cloudinary.config().cloud_name

        update_config({config_name: cloudinary_url})

        logger.info("Config '{}' saved!".format(config_name))
        logger.info("Example usage: cld -C {} <command>".format(config_name))
    elif rm:
        if remove_config_keys(rm):
            logger.warn(f"Configuration '{rm}' not found.")
        else:
            logger.info(f"Configuration '{rm}' deleted")
    elif ls:
        echo("\n".join(load_config().keys()))
    else:
        obfuscated_config = {k: v if k != "api_secret" else "***************{}".format(v[-4:])
                             for k, v in cloudinary.config().__dict__.items()}
        echo('\n'.join(["{}:\t{}".format(k, v) for k, v in obfuscated_config.items()]))
