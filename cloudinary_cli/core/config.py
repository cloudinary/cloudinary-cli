import cloudinary
from click import command, option, echo, BadParameter

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import load_config, verify_cloudinary_url, update_config, remove_config_keys, \
    show_cloudinary_config


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
def config(new, ls, show, rm, from_url):
    if new or from_url:
        config_name, cloudinary_url = new or [None, from_url]

        if not verify_cloudinary_url(cloudinary_url):
            return False

        config_name = config_name or cloudinary.config().cloud_name

        update_config({config_name: cloudinary_url})

        logger.info("Config '{}' saved!".format(config_name))
        logger.info("Example usage: cld -C {} <command>".format(config_name))
    elif rm:
        if remove_config_keys(rm):
            logger.warning(f"Configuration '{rm}' not found.")
        else:
            logger.info(f"Configuration '{rm}' deleted.")
    elif ls:
        echo("\n".join(load_config().keys()))
    elif show:
        curr_config = load_config()
        if show not in curr_config:
            raise BadParameter(f"Configuration {show} does not exist, use -ls to list available configurations.")

        config_obj = cloudinary.Config()
        # noinspection PyProtectedMember
        config_obj._setup_from_parsed_url(config_obj._parse_cloudinary_url(load_config()[show]))

        return show_cloudinary_config(config_obj)
    else:
        return show_cloudinary_config(cloudinary.config())
