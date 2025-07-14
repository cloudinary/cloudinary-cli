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
ALLOWED_TYPE_VALUES = ("upload", "private", "authenticated")


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
@option("-ue", "--url_expiry", type=int, default=3600,
        help=("URL expiration duration in seconds. Only relevant if cloning "
              "restricted assets with an auth_key configured. "
              "If you do not provide an auth_key, "
              "a private download URL is generated which may incur additional "
              "bandwidth costs."))
def clone(target, force, overwrite, concurrent_workers, fields,
          search_exp, async_, notification_url, url_expiry):
    target_config, auth_token = _validate_clone_inputs(target)
    if not target_config:
        return False

    source_assets = search_assets(search_exp, force)
    if not source_assets:
        return False
    if not isinstance(source_assets, dict) or not source_assets.get('resources'):
        logger.error(style(f"No asset(s) found in {cloudinary.config().cloud_name}", fg="red"))
        return False

    upload_list = _prepare_upload_list(
        source_assets, target_config, overwrite, async_,
        notification_url, auth_token, url_expiry, fields
    )

    logger.info(style(f"Copying {len(upload_list)} asset(s) from "
                      f"{cloudinary.config().cloud_name} to "
                      f"{target_config.cloud_name}", fg="blue"))

    run_tasks_concurrently(upload_file, upload_list, concurrent_workers)

    return True


def _validate_clone_inputs(target):
    if not target:
        print_help_and_exit()

    target_config = get_cloudinary_config(target)
    if not target_config:
        logger.error("The specified config does not exist or the "
                     "CLOUDINARY_URL scheme provided is invalid "
                     "(expecting to start with 'cloudinary://').")
        return None, None

    if cloudinary.config().cloud_name == target_config.cloud_name:
        logger.error("Target environment cannot be the same "
                     "as source environment.")
        return None, None

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
            return None, None

    return target_config, auth_token


def _prepare_upload_list(source_assets, target_config, overwrite, async_,
                         notification_url, auth_token, url_expiry, fields):
    upload_list = []
    for r in source_assets.get('resources'):
        updated_options, asset_url = process_metadata(r, overwrite, async_,
                                                      notification_url,
                                                      auth_token, url_expiry,
                                                      normalize_list_params(fields))
        updated_options.update(config_to_dict(target_config))
        upload_list.append((asset_url, {**updated_options}))
    return upload_list


def search_assets(search_exp, force):
    search_exp = _normalize_search_expression(search_exp)
    if not search_exp:
        return False

    search = cloudinary.search.Search().expression(search_exp)
    search.fields(['tags', 'context', 'access_control',
                   'secure_url', 'display_name', 'format'])
    search.max_results(DEFAULT_MAX_RESULTS)

    res = execute_single_request(search, fields_to_keep="")
    res = handle_auto_pagination(res, search, force, fields_to_keep="")

    return res


def _normalize_search_expression(search_exp):
    """
    Ensures the search expression has a valid 'type' filter.

    - If no expression is given, a default is created.
    - If 'type' filters exist, they are validated.
    - If no 'type' filters exist, the default is appended.
    """
    default_types_str = " OR ".join(f"type:{t}" for t in ALLOWED_TYPE_VALUES)

    if not search_exp:
        return default_types_str

    # Use a simple regex to find all 'type' filters
    found_types = re.findall(r"\btype\s*[:=]\s*(\w+)", search_exp)

    if not found_types:
        # No 'type' filter found, so append the default
        return f"{search_exp} AND ({default_types_str})"

    # A 'type' filter was found, so validate it
    invalid_types = {t for t in found_types if t not in ALLOWED_TYPE_VALUES}

    if invalid_types:
        error_msg = ", ".join(f"type:{t}" for t in invalid_types)
        logger.error(
            f"Unsupported type(s) in search expression: {error_msg}. "
            f"Only {', '.join(ALLOWED_TYPE_VALUES)} types allowed."
        )
        return None

    # All found types are valid, so return the original expression
    return search_exp


def process_metadata(res, overwrite, async_, notification_url, auth_token, url_expiry, copy_fields=None):
    if copy_fields is None:
        copy_fields = []
    asset_url = _get_asset_url(res, auth_token, url_expiry)
    cloned_options = _build_cloned_options(res, overwrite, async_, notification_url, copy_fields)

    return cloned_options, asset_url


def _get_asset_url(res, auth_token, url_expiry):
    if not (isinstance(res.get('access_control'), list) and
            len(res.get('access_control')) > 0 and
            isinstance(res['access_control'][0], dict) and
            res['access_control'][0].get("access_type") == "token"):
        return res.get('secure_url')

    reso_type = res.get('resource_type')
    del_type = res.get('type')
    pub_id = res.get('public_id')
    file_format = res.get('format')

    if auth_token:
        # Raw assets already have the format in the public_id
        pub_id_format = pub_id if reso_type == "raw" else f"{pub_id}.{file_format}"
        return cloudinary.utils.cloudinary_url(
            pub_id_format,
            type=del_type,
            resource_type=reso_type,
            auth_token={"duration": url_expiry},
            secure=True,
            sign_url=True
        )

    # Use private url if no auth_token provided
    return cloudinary.utils.private_download_url(
        pub_id,
        file_format,
        resource_type=reso_type,
        type=del_type,
        expires_at=int(time.time()) + url_expiry
    )


def _build_cloned_options(res, overwrite, async_, notification_url, copy_fields):
    # 1. Start with mandatory options
    cloned_options = {
        'overwrite': overwrite,
        'async': async_,
    }

    # 2. Copy fields from source asset. Some are standard, others are from user input.
    fields_to_copy = {'public_id', 'type', 'resource_type', 'access_control'}.union(copy_fields)
    cloned_options.update({field: res.get(field) for field in fields_to_copy})

    # 3. Handle fields that are added only if they have a truthy value
    if res.get('display_name'):
        cloned_options['display_name'] = res['display_name']

    # This is required to put the asset in the correct asset_folder
    # when copying from a fixed to DF (dynamic folder) cloud as if
    # you just pass a `folder` param to a DF cloud, it will append
    # this to the `public_id` and we don't want this.
    if res.get('folder'):
        cloned_options['asset_folder'] = res['folder']
    elif res.get('asset_folder'):
        cloned_options['asset_folder'] = res['asset_folder']

    if notification_url:
        cloned_options['notification_url'] = notification_url

    # 4. Clean up any None values before returning
    return {k: v for k, v in cloned_options.items() if v is not None}
