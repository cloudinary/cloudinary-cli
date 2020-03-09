import json

import cloudinary
from click import command, option
from cloudinary import api

from cloudinary_cli.utils import CLOUDINARY_CLI_CONFIG_FILE, refresh_config, logger


@command("config", help="Display the current configuration, and manage additional configurations.")
@option("-n", "--new", help="""\b Create and name a configuration from a Cloudinary account environment variable.
e.g. cld config -n <NAME> <CLOUDINARY_URL>""", nargs=2)
@option("-ls", "--ls", help="List all saved configurations.", is_flag=True)
@option("-rm", "--rm", help="Delete a specified configuration.", nargs=1)
@option("-url", "--from_url", help="Create a configuration from a Cloudinary account environment variable. The configuration name is the cloud name.", nargs=1)
def config(new, ls, rm, from_url):
    if not (new or ls or rm or from_url):
        logger.info('\n'.join(["{}:\t{}".format(k, v if k != "api_secret"
        else "***************{}".format(v[-4:]))
                               for k, v in cloudinary.config().__dict__.items()]))
        return

    with open(CLOUDINARY_CLI_CONFIG_FILE, "r+") as f:
        fi = f.read()
        cfg = json.loads(fi) if fi != "" else {}
        f.close()
    if new:
        try:
            refresh_config(new[1])
            cfg[new[0]] = new[1]
            api.ping()
            with open(CLOUDINARY_CLI_CONFIG_FILE, "w") as f:
                f.write(json.dumps(cfg))
                f.close()
            logger.info("Config '{}' saved!".format(new[0]))
        except Exception as e:
            logger.error("Invalid Cloudinary URL: {}".format(new[1]))
            raise e
        return
    if ls:
        logger.info("\n".join(cfg.keys()))
    if rm:
        if rm not in cfg.keys():
            logger.warn("Configuration '{}' not found.".format(rm))
            return
        del cfg[rm]
        open(CLOUDINARY_CLI_CONFIG_FILE, "w").write(json.dumps(cfg))
        logger.info("Configuration '{}' deleted".format(rm))
        return
    if from_url:
        if "CLOUDINARY_URL=" in from_url:
            from_url = from_url[15:]
        try:
            refresh_config(from_url)
            cfg[cloudinary.config().cloud_name] = from_url
            api.ping()
            with open(CLOUDINARY_CLI_CONFIG_FILE, "w") as f:
                f.write(json.dumps(cfg))
                f.close()
            logger.info("Config '{}' saved!".format(cloudinary.config().cloud_name))
            logger.info("Example usage: cld -C {} <command>".format(cloudinary.config().cloud_name))
        except Exception as e:
            logger.error("Invalid Cloudinary URL: {}".format(from_url))
            raise e
