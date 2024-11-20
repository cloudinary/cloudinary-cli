from click import command, option, style
from cloudinary_cli.utils.utils import normalize_list_params, \
     print_help_and_exit
import cloudinary
from cloudinary_cli.utils.utils import run_tasks_concurrently
from cloudinary_cli.utils.api_utils import upload_file
from cloudinary_cli.utils.config_utils import load_config
from cloudinary_cli.defaults import logger
from cloudinary_cli.core.search import execute_single_request, \
     handle_auto_pagination

DEFAULT_MAX_RESULTS = 500


@command("clone",
         short_help="""Clone assets from one account to another.""",
         help="""
\b
Clone assets from one environment to another with/without tags and/or context (structured metadata is not currently supported).
Source will be your `CLOUDINARY_URL` environemnt variable but you also can specify a different source using `-c/-C` option.
Cloning restricted assets is also not supported currently.
Format: cld clone -T <target_environment> <command options>
`<target_environment>` can be a CLOUDINARY_URL or a saved config (see  `config` command)
e.g. cld clone -T cloudinary://<api_key>:<api_secret>@<cloudname> -f tags,context
""")
@option("-T", "--target",
        help="Tell the CLI the target environemnt to run the command on.")
@option("-F", "--force", is_flag=True,
        help="Skip confirmation.")
@option("-O", "--overwrite", is_flag=True, default=False,
        help="Specify whether to overwrite existing assets.")
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
def clone(target, force, overwrite, concurrent_workers, fields, search_exp,
          async_, notification_url):
    if not target:
        print_help_and_exit()

    target_config = cloudinary.Config()
    is_cloudinary_url = False
    if target.startswith("cloudinary://"):
        is_cloudinary_url = True
        parsed_url = target_config._parse_cloudinary_url(target)
    elif target in load_config():
        parsed_url = target_config._parse_cloudinary_url(load_config().get(target))
    else:
        logger.error("The specified config does not exist or the "
                     "CLOUDINARY_URL scheme provided is invalid "
                     "(expecting to start with 'cloudinary://').")
        return False

    target_config._setup_from_parsed_url(parsed_url)
    target_config_dict = {k: v for k, v in target_config.__dict__.items()
                          if not k.startswith("_")}
    if is_cloudinary_url:
        try:
            cloudinary.api.ping(**target_config_dict)
        except Exception as e:
            logger.error(f"{e}. Please double-check your Cloudinary URL.")
            return False

    source_cloudname = cloudinary.config().cloud_name
    target_cloudname = target_config.cloud_name
    if source_cloudname == target_cloudname:
        logger.info("Target environment cannot be the "
                    "same as source environment.")
        return True

    copy_fields = normalize_list_params(fields)
    search = cloudinary.search.Search().expression(search_exp)
    search.fields(['tags', 'context', 'access_control',
                   'secure_url', 'display_name'])
    search.max_results(DEFAULT_MAX_RESULTS)
    res = execute_single_request(search, fields_to_keep="")
    res = handle_auto_pagination(res, search, force, fields_to_keep="")

    upload_list = []
    for r in res.get('resources'):
        updated_options, asset_url = process_metadata(r, overwrite, async_,
                                                      notification_url,
                                                      copy_fields)
        updated_options.update(target_config_dict)
        upload_list.append((asset_url, {**updated_options}))

    logger.info(style(f'Copying {len(upload_list)} asset(s) to '
                      f'{target_cloudname}', fg="blue"))
    run_tasks_concurrently(upload_file, upload_list,
                           concurrent_workers)

    return True


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
