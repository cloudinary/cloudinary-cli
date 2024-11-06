from click import command, option, style
from cloudinary_cli.utils.utils import normalize_list_params, \
     print_help_and_exit
import cloudinary
from cloudinary_cli.utils.utils import run_tasks_concurrently
from cloudinary_cli.utils.api_utils import upload_file
from cloudinary_cli.utils.config_utils import load_config, \
     refresh_cloudinary_config, verify_cloudinary_url
from cloudinary_cli.defaults import logger
from cloudinary_cli.core.search import execute_single_request, \
     handle_auto_pagination
import os

DEFAULT_MAX_RESULTS = 500


@command("clone",
         short_help="""Clone assets from one account to another.""",
         help="""
\b
Clone assets from one environment to another with/without tags and context (structured metadata is not currently supported).
Source will be your `CLOUDINARY_URL` environemnt variable but you also can specify a different source using `-c/-C` option.
Cloning restricted assets is also not supported currently.
Format: cld clone -t/-T <target_environemnt> <command options>
You need to specify the target cloud via `-t` or `-T` (not both)
e.g. cld clone -t cloudinary://<api_key>:<api_secret>@<cloudname> -f tags,context -O
""")
@option("-T", "--target_saved",
        help="Tell the CLI the target environemnt to run the command on by specifying a saved configuration - see `config` command.")
@option("-t", "--target",
        help="Tell the CLI the target environemnt to run the command on by specifying an environment variable.")
@option("-A", "--auto_paginate", is_flag=True, default=False,
        help="Auto-paginate Admin API calls.")
@option("-F", "--force", is_flag=True,
        help="Skip confirmation.")
@option("-O", "--overwrite", is_flag=True, default=False,
        help="Skip confirmation.")
@option("-w", "--concurrent_workers", type=int, default=30,
        help="Specify the number of concurrent network threads.")
@option("-f", "--fields", multiple=True,
        help="Specify whether to copy tags and context.")
@option("-se", "--search_exp", default="",
        help="Define a search expression.")
@option("--async", "async_", is_flag=True, default=False,
        help="Generate asynchronously.")
@option("-nu", "--notification_url",
        help="Webhook notification URL.")
def clone(target_saved, target, auto_paginate, force,
          overwrite, concurrent_workers, fields, search_exp,
          async_, notification_url):
    if bool(target) == bool(target_saved):
        print_help_and_exit()

    base_cloudname_url = os.environ.get('CLOUDINARY_URL')
    base_cloudname = cloudinary.config().cloud_name
    if target:
        verify_cloudinary_url(target)
    elif target_saved:
        config = load_config()
        if target_saved not in config:
            logger.error(f"Config {target_saved} does not exist")
            return False
        else:
            refresh_config(target_saved=target_saved)
    target_cloudname = cloudinary.config().cloud_name
    if base_cloudname == target_cloudname:
        logger.info("Target environment cannot be the "
                    "same as source environment.")
        return True
    refresh_config(base_cloudname_url)

    copy_fields = normalize_list_params(fields)
    search = cloudinary.search.Search().expression(search_exp)
    search.fields(['tags', 'context', 'access_control',
                   'secure_url', 'display_name'])
    search.max_results(DEFAULT_MAX_RESULTS)
    res = execute_single_request(search, fields_to_keep="")
    if auto_paginate:
        res = handle_auto_pagination(res, search, force, fields_to_keep="")

    upload_list = []
    for r in res.get('resources'):
        updated_options, asset_url = process_metadata(r, overwrite, async_,
                                                      notification_url,
                                                      copy_fields)
        upload_list.append((asset_url, {**updated_options}))

    refresh_config(target, target_saved)
    logger.info(style(f'Copying {len(upload_list)} asset(s) to '
                      f'{target_cloudname}', fg="blue"))
    run_tasks_concurrently(upload_file, upload_list,
                           concurrent_workers)

    return True


def refresh_config(target="", target_saved=""):
    if target:
        refresh_cloudinary_config(target)
    elif target_saved:
        refresh_cloudinary_config(load_config()[target_saved])


def process_metadata(res, overwrite, async_, notification_url, copy_fields=""):
    cloned_options = {}
    asset_url = res.get('secure_url')
    cloned_options['public_id'] = res.get('public_id')
    cloned_options['type'] = res.get('type')
    cloned_options['resource_type'] = res.get('resource_type')
    cloned_options['overwrite'] = overwrite
    cloned_options['async'] = async_
    if "tags" in copy_fields:
        cloned_options['tags'] = res.get('tags')
    if "context" in copy_fields:
        cloned_options['context'] = res.get('context')
    if res.get('folder'):
        cloned_options['asset_folder'] = res.get('folder')
    elif res.get('asset_folder'):
        cloned_options['asset_folder'] = res.get('asset_folder')
    if res.get('display_name'):
        cloned_options['display_name'] = res.get('display_name')
    if notification_url:
        cloned_options['notification_url'] = notification_url

    return cloned_options, asset_url
