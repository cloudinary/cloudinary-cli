from click import command, argument, option, style
from cloudinary_cli.utils.utils import group_params, parse_option_value, \
     normalize_list_params
import cloudinary
from cloudinary_cli.utils.utils import confirm_action, run_tasks_concurrently
from cloudinary_cli.utils.api_utils import upload_file
from binascii import a2b_hex
from cloudinary_cli.utils.config_utils import load_config, \
     refresh_cloudinary_config, verify_cloudinary_url
from cloudinary_cli.defaults import logger
import copy as deepcopy_module
from cloudinary_cli.core.search import execute_single_request, \
     handle_auto_pagination

DEFAULT_MAX_RESULTS = 500


@command("clone",
         short_help="""Clone assets, structured metadata, upload preset or named transformations from one account to another.""",
         help="tbc")
@argument("search_exp", nargs=-1)
@option("-T", "--target_saved",
        help="Tell the CLI the target environemnt to run the command on by specifying a saved configuration - see `config` command.")
@option("-t", "--target",
        help="Tell the CLI the target environemnt to run the command on by specifying an account environment variable.")
@option("-A", "--auto_paginate", is_flag=True, default=False,
        help="Auto-paginate Admin API calls.")
@option("-F", "--force", is_flag=True,
        help="Skip confirmation.")
@option("-n", "--max_results", nargs=1, default=10,
        help="""The maximum number of results to return.
              Default: 10, maximum: 500.""")
@option("-o", "--optional_parameter", multiple=True, nargs=2,
        help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-w", "--concurrent_workers", type=int, default=30,
        help="Specify the number of concurrent network threads.")
@option("--fields", multiple=True, help="Specify whether to copy tags and context")
@option("-at", "--auth_token", help="Authentication token for base environment. Used for generating a token for assets that have access control.")
def clone(search_exp, target_saved, target, auto_paginate, force, max_results,
          optional_parameter, optional_parameter_parsed, concurrent_workers,
          auth_token, fields):

    if not target and not target_saved:
        print("Target (-T/-t) is mandatory. ")
        exit()
    elif target and target_saved:
        print("Please pass either -t or -T, not both.")
        exit()

    if target:
        verify_cloudinary_url(target)
    elif target_saved:
        config = load_config()
        if target_saved not in config:
            raise Exception(f"Config {target_saved} does not exist")

    if fields:
        copy_fields = normalize_list_params(fields)
    else:
        copy_fields = ""

    if auth_token:
        try:
            a2b_hex(auth_token)
        except Exception:
            print('Auth key is not valid. Please double-check.')
            exit()
    else:
        auth_token = ""

    search = cloudinary.search.Search().expression(" ".join(search_exp))
    if auto_paginate:
        max_results = DEFAULT_MAX_RESULTS
    search.fields(['tags', 'context', 'access_control',
                   'secure_url', 'display_name'])
    search.max_results(max_results)
    res = execute_single_request(search, fields_to_keep="")
    if auto_paginate:
        res = handle_auto_pagination(res, search, force, fields_to_keep="")

    options = {
        **group_params(optional_parameter,
                       ((k, parse_option_value(v))
                        for k, v in optional_parameter_parsed)),
    }

    upload_list = []
    for r in res.get('resources'):
        updated_options, asset_url = process_metadata(r, auth_token, options,
                                                      copy_fields)
        upload_list.append((asset_url, {**updated_options}))

    base_cloudname = cloudinary.config().cloud_name
    if target:
        refresh_cloudinary_config(target)
    elif target_saved:
        refresh_cloudinary_config(load_config()[target_saved])
    target_cloudname = cloudinary.config().cloud_name

    if base_cloudname == target_cloudname:
        if not confirm_action(
                "Target environment is same as base cloud. "
                "Continue? (y/N)"):
            logger.info("Stopping.")
            exit()
        else:
            logger.info("Continuing.")
    logger.info(style(f'Copying {len(upload_list)} asset(s) to '
                      f'{target_cloudname}', fg="blue"))
    run_tasks_concurrently(upload_file, upload_list,
                           concurrent_workers)

    return True


def process_metadata(res, auth_t, options, copy_fields):
    cloned_options = deepcopy_module.deepcopy(options)
    if res.get('access_control'):
        asset_url = generate_token(res.get('public_id'), res.get('type'),
                                   res.get('resource_type'), res.get('format'),
                                   auth_t)
        cloned_options['access_control'] = res.get('access_control')
    else:
        asset_url = res.get('secure_url')
    cloned_options['public_id'] = res.get('public_id')
    cloned_options['type'] = res.get('type')
    cloned_options['resource_type'] = res.get('resource_type')
    if not cloned_options.get('overwrite'):
        cloned_options['overwrite'] = True
    if "tags" in copy_fields:
        cloned_options['tags'] = res.get('tags')
    if "context" in copy_fields:
        cloned_options['context'] = res.get('context')
    if res.get('folder') and not cloned_options.get('asset_folder'):
        cloned_options['asset_folder'] = res.get('folder')
    elif res.get('asset_folder') and not cloned_options.get('asset_folder'):
        cloned_options['asset_folder'] = res.get('asset_folder')
    if res.get('display_name'):
        cloned_options['display_name'] = res.get('display_name')
    return cloned_options, asset_url


def generate_token(pid, type, r_type, format, auth_t):
    url = cloudinary.utils.cloudinary_url(
        f"{pid}.{format}",
        type=type,
        resource_type=r_type,
        auth_token=dict(key=auth_t,
                        duration=30),
        secure=True,
        sign_url=True,
        force_version=False)
    return url
