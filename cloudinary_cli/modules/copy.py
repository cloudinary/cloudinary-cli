from click import command, argument, option, style
from cloudinary_cli.utils.utils import group_params, parse_option_value, \
     normalize_list_params
import cloudinary
from cloudinary_cli.utils.utils import confirm_action, run_tasks_concurrently
from cloudinary_cli.utils.json_utils import read_json_from_file
from cloudinary_cli.utils.api_utils import upload_file
from binascii import a2b_hex
from .sync import sync
from click.testing import CliRunner
from cloudinary_cli.utils.config_utils import load_config, \
     refresh_cloudinary_config
import os
from cloudinary_cli.defaults import logger
import copy as deepcopy_module


@command("copy",
         short_help="""Copy assets, structured metadata, upload preset or named transformations from one account to another.""",
         help="tbc")
@argument("search_exp")
@option("-T", "--target", multiple=True,
        help="Tell the CLI the target environemnt to run the command on by specifying a saved configuration - see `config` command.")
@option("-o", "--optional_parameter", multiple=True, nargs=2,
        help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-w", "--concurrent_workers", type=int, default=30,
        help="Specify the number of concurrent network threads.")
@option("-at", "--auth_token", help="Authentication token for base environment. Used for generating a token for assets that have access control.")
@option("-ct", "--copy_tags", is_flag=True,
        help="Copy tags.")
@option("-cc", "--copy_context", is_flag=True,
        help="Copy context.")
@option("-cm", "--copy_metadata", is_flag=True,
        help="Copy metadata. Make sure to create the metadata in the traget account beforehand with the same external id")
@option("-usj", "--use_saved_json", is_flag=True,
        help="Use the saved json file if you want to skip the initial search.")
def copy(search_exp, target, optional_parameter, optional_parameter_parsed,
         concurrent_workers, auth_token, copy_tags, copy_context,
         copy_metadata, use_saved_json):

    if not target:
        print("-T/--target is mandatory. ")
        exit()

    target = normalize_list_params(target)
    for val in target:
        config = load_config()
        if val not in config:
            raise Exception(f"Config {val} does not exist")

    if auth_token:
        try:
            a2b_hex(auth_token)
        except Exception:
            print('Auth key is not valid. Please double-check.')
            exit()
    else:
        auth_token = ""

    if use_saved_json and os.path.exists("assets_to_copy.json"):
        logger.info('Using assets_to_copy.json...')
        res = read_json_from_file("assets_to_copy.json")
    else:
        logger.info('Searching assets...')
        runner = CliRunner()
        runner.invoke(sync, ['from_copy_module', search_exp,
                             '--pull',
                             '--is_search_expression'], catch_exceptions=False)
        res = read_json_from_file("assets_to_copy.json")

    options = {
        **group_params(optional_parameter,
                       ((k, parse_option_value(v))
                        for k, v in optional_parameter_parsed)),
    }

    upload_list = []
    for r in res:
        updated_options, asset_url = process_metadata(r, auth_token, options,
                                                      copy_tags, copy_context,
                                                      copy_metadata)
        upload_list.append((asset_url, {**updated_options}))

    base_cloudname = cloudinary.config().cloud_name
    for val in target:
        refresh_cloudinary_config(config[val])
        target_cloudname = cloudinary.config().cloud_name
        if base_cloudname == target_cloudname:
            if not confirm_action(
                    "Target environment is same as base cloud. "
                    "Continue? (y/N)"):
                logger.info("Stopping.")
                exit()
            else:
                logger.info("Continuing.")
        logger.info(style(f'Copying {len(upload_list)} asset(s) to {val}',
                          fg="blue"))
        run_tasks_concurrently(upload_file, upload_list,
                               concurrent_workers)

    return True


def process_metadata(res, auth_t, options, copy_tags, copy_context,
                     copy_metadata):
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
    if copy_tags:
        cloned_options['tags'] = res.get('tags')
    if copy_context:
        cloned_options['context'] = res.get('context')
    if copy_metadata:
        cloned_options['metadata'] = res.get('metadata')
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
