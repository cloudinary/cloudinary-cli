from click import command, option, style, argument
from cloudinary_cli.utils.utils import normalize_list_params, print_help_and_exit
import cloudinary
from cloudinary_cli.utils.utils import run_tasks_concurrently
from cloudinary_cli.utils.api_utils import upload_file
from cloudinary_cli.utils.config_utils import load_config, get_cloudinary_config, config_to_dict
from cloudinary_cli.defaults import logger
from cloudinary_cli.core.search import execute_single_request, handle_auto_pagination

DEFAULT_MAX_RESULTS = 500


@command("clone",
         short_help="""Clone assets from one product environment to another.""",
         help="""
\b
Clone assets from one product environment to another with/without tags and/or context (structured metadata is not currently supported).
Source will be your `CLOUDINARY_URL` environment variable but you also can specify a different source using the `-c/-C` option.
Cloning restricted assets is also not supported currently.
Format: cld clone <target_environment> <command options>
`<target_environment>` can be a CLOUDINARY_URL or a saved config (see `config` command)
Example 1 (Copy all assets including tags and context using CLOUDINARY URL):
    cld clone cloudinary://<api_key>:<api_secret>@<cloudname> -fi tags,context
Example 2 (Copy all assets with a specific tag via a search expression using a saved config):
    cld clone <config_name> -se "tags:<tag_name>"
""")
@argument("target")
@option("-F", "--force", is_flag=True,
        help="Skip confirmation.")
@option("-ow", "--overwrite", is_flag=True, default=False,
        help="Specify whether to overwrite existing assets.")
@option("-w", "--concurrent_workers", type=int, default=30,
        help="Specify the number of concurrent network threads.")
@option("-fi", "--fields", multiple=True,
        help="Specify whether to copy tags and/or context. Valid options: `tags,context`.")
@option("-se", "--search_exp", default="",
        help="Define a search expression to filter the assets to clone.")
@option("--async", "async_", is_flag=True, default=False,
        help="Clone the assets asynchronously.")
@option("-nu", "--notification_url",
        help="Webhook notification URL.")
def clone(target, force, overwrite, concurrent_workers, fields, search_exp, async_, notification_url):
    if not target:
        print_help_and_exit()

    target_config = get_cloudinary_config(target)
    if not target_config:
        logger.error("The specified config does not exist or the CLOUDINARY_URL scheme provided is invalid"
                     " (expecting to start with 'cloudinary://').")
        return False

    if cloudinary.config().cloud_name == target_config.cloud_name:
        logger.error("Target environment cannot be the same as source environment.")
        return False

    source_assets = search_assets(force, search_exp)

    upload_list = []
    for r in source_assets.get('resources'):
        updated_options, asset_url = process_metadata(r, overwrite, async_, notification_url,
                                                      normalize_list_params(fields))
        updated_options.update(config_to_dict(target_config))
        upload_list.append((asset_url, {**updated_options}))

    if not upload_list:
        logger.error(style(f'No assets found in {cloudinary.config().cloud_name}', fg="red"))
        return False

    logger.info(style(f'Copying {len(upload_list)} asset(s) from {cloudinary.config().cloud_name} to {target_config.cloud_name}', fg="blue"))

    run_tasks_concurrently(upload_file, upload_list, concurrent_workers)

    return True


def search_assets(force, search_exp):
    search = cloudinary.search.Search().expression(search_exp)
    search.fields(['tags', 'context', 'access_control', 'secure_url', 'display_name'])
    search.max_results(DEFAULT_MAX_RESULTS)

    res = execute_single_request(search, fields_to_keep="")
    res = handle_auto_pagination(res, search, force, fields_to_keep="")

    return res


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
        # This is required to put the asset in the correct asset_folder
        # when copying from a fixed to DF (dynamic folder) cloud as if
        # you just pass a `folder` param to a DF cloud, it will append
        # this to the `public_id` and we don't want this.
        cloned_options['asset_folder'] = res.get('folder')
    elif res.get('asset_folder'):
        cloned_options['asset_folder'] = res.get('asset_folder')
    if res.get('display_name'):
        cloned_options['display_name'] = res.get('display_name')
    if notification_url:
        cloned_options['notification_url'] = notification_url

    return cloned_options, asset_url
