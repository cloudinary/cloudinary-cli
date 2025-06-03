from click import command, option, style, argument
from cloudinary_cli.utils.utils import normalize_list_params, print_help_and_exit
import cloudinary
from cloudinary.auth_token import _digest
from cloudinary_cli.utils.utils import run_tasks_concurrently
from cloudinary_cli.utils.api_utils import upload_file
from cloudinary_cli.utils.config_utils import get_cloudinary_config, config_to_dict
from cloudinary_cli.defaults import logger
from cloudinary_cli.core.search import execute_single_request, handle_auto_pagination
import time
import re

DEFAULT_MAX_RESULTS = 500


@command("clone",
         short_help="""Clone assets from one product environment to another.""",
         help="""
\b
Clone assets from one product environment to another with/without tags and/or context (structured metadata is not currently supported).
Source will be your `CLOUDINARY_URL` environment variable but you also can specify a different source using the `-c/-C` option.
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
        help=("Specify whether to copy tags and/or context. "
              "Valid options: `tags,context`."))
@option("-se", "--search_exp", default="",
        help="Define a search expression to filter the assets to clone.")
@option("--async", "async_", is_flag=True, default=False,
        help="Clone the assets asynchronously.")
@option("-nu", "--notification_url",
        help="Webhook notification URL.")
@option("-t", "--ttl", type=int, default=3600,
        help=("URL expiration duration in seconds. Only relevant if cloning "
              "restricted assets. If you do not provide an auth_key, "
              "a private download URL is generated which may incur additional "
              "bandwidth costs."))
def clone(target, force, overwrite, concurrent_workers, fields,
          search_exp, async_, notification_url, ttl):
    if not target:
        print_help_and_exit()

    target_config = get_cloudinary_config(target)
    if not target_config:
        logger.error("The specified config does not exist or the "
                     "CLOUDINARY_URL scheme provided is invalid "
                     "(expecting to start with 'cloudinary://').")
        return False

    if cloudinary.config().cloud_name == target_config.cloud_name:
        logger.error("Target environment cannot be the same "
                     "as source environment.")
        return False

    auth_token = cloudinary.config().auth_token
    if auth_token:
        # It is important to validate auth_token if provided as this prevents
        # customer from having to re-run the command as well as
        # saving Admin API calls and time.
        try:
            cloudinary.utils.generate_auth_token(acl="/image/*")
        except Exception as e:
            logger.error(f"{e} - auth_token validation failed. "
                         "Please double-check your auth_token parameters.")
            return False

    source_assets = search_assets(force, search_exp)
    if not source_assets:
        # End command if search_exp contains unsupported type(s)
        return False

    upload_list = []
    for r in source_assets.get('resources'):
        updated_options, asset_url = process_metadata(r, overwrite, async_,
                                                      notification_url,
                                                      auth_token, ttl,
                                                      normalize_list_params(fields))
        updated_options.update(config_to_dict(target_config))
        upload_list.append((asset_url, {**updated_options}))

    source_cloud_name = cloudinary.config().cloud_name
    if not upload_list:
        logger.error(style('No asset(s) found in '
                           f'{source_cloud_name}', fg="red"))
        return False

    logger.info(style(f'Copying {len(upload_list)} asset(s) from '
                      f'{source_cloud_name} to '
                      f'{target_config.cloud_name}', fg="blue"))

    run_tasks_concurrently(upload_file, upload_list, concurrent_workers)

    return True


def search_assets(force, search_exp):
    # Prevent other unsupported types to prevent
    # avoidable errors during the upload process
    # and append the default types in not in the
    # search expression
    ALLOWED_TYPES = {"type:upload", "type:private", "type:authenticated",
                     "type=upload", "type=private", "type=authenticated"}
    if search_exp and re.search(r"\btype\s*[:=]\s*\w+", search_exp):
        exp_types = re.findall(r"\btype\s*[:=]\s*\w+", search_exp)
        exp_types_cleaned = [''.join(t.split()) for t in exp_types]
        unallowed_types = [t for t in exp_types_cleaned if t not in ALLOWED_TYPES]
        if unallowed_types:
            logger.error("Unsupported type(s) in search expression: "
                         f"{', '.join(unallowed_types)}. "
                         "Only upload/private/authenticated types allowed.")
            return False
    elif search_exp:
        search_exp += " AND (type:upload OR type:private OR type:authenticated)"
    else:
        search_exp = "type:upload OR type:private OR type:authenticated"

    search = cloudinary.search.Search().expression(search_exp)
    search.fields(['tags', 'context', 'access_control',
                   'secure_url', 'display_name', 'format'])
    search.max_results(DEFAULT_MAX_RESULTS)

    res = execute_single_request(search, fields_to_keep="")
    res = handle_auto_pagination(res, search, force, fields_to_keep="")

    return res


def process_metadata(res, overwrite, async_, notification_url,
                     auth_token, ttl, copy_fields=""):
    cloned_options = {}
    acc_ctl = res.get('access_control')
    pub_id = res.get('public_id')
    del_type = res.get('type')
    reso_type = res.get('resource_type')
    file_format = res.get('format')
    if (
        isinstance(acc_ctl, list)
        and len(acc_ctl) > 0
        and isinstance(acc_ctl[0], dict)
        and acc_ctl[0].get("access_type") == "token"
    ):
        # Generate a time-limited URL for restricted assets
        # Use private url if no auth_token provided
        if auth_token:
            # Don't add format if asset is raw
            pub_id_format = (pub_id if reso_type == "raw"
                             else f"{pub_id}.{file_format}")
            asset_url = cloudinary.utils.cloudinary_url(
                            pub_id_format,
                            type=del_type,
                            resource_type=reso_type,
                            auth_token={"duration": ttl},
                            secure=True,
                            sign_url=True)
        else:
            expiry_date = int(time.time()) + ttl
            asset_url = cloudinary.utils.private_download_url(
                            pub_id,
                            file_format,
                            resource_type=reso_type,
                            type=del_type,
                            expires_at=expiry_date)
    else:
        asset_url = res.get('secure_url')
    cloned_options['access_control'] = acc_ctl
    cloned_options['public_id'] = pub_id
    cloned_options['type'] = del_type
    cloned_options['resource_type'] = reso_type
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
