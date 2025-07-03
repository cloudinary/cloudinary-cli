from click import command, option, style, argument
from cloudinary_cli.utils.utils import normalize_list_params, print_help_and_exit
import cloudinary
from cloudinary_cli.utils.utils import run_tasks_concurrently
from cloudinary_cli.utils.api_utils import upload_file, handle_api_command
from cloudinary_cli.utils.json_utils import print_json
from cloudinary_cli.utils.config_utils import load_config, get_cloudinary_config, config_to_dict, config_to_tuple_list
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
        help="Specify whether to copy tags and/or context. Valid options: `tags,context,metadata`.")
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
    if 'metadata' in fields:
        source_metadata = list_metadata_items("metadata_fields")
        if source_metadata.get('metadata_fields'):
            target_metadata = list_metadata_items("metadata_fields", config_to_tuple_list(target_config))
            fields_compare = compare_create_metadata_items(source_metadata, target_metadata, config_to_tuple_list(target_config), key="metadata_fields")
            source_metadata_rules = list_metadata_items("metadata_rules")
            if source_metadata_rules.get('metadata_rules'):
                target_metadata_rules = list_metadata_items("metadata_rules", config_to_tuple_list(target_config))
                rules_compare = compare_create_metadata_items(source_metadata_rules,target_metadata_rules, config_to_tuple_list(target_config), key="metadata_rules", id_field="name")
            else:
                logger.info(style(f"No metadata rules found in {cloudinary.config().cloud_name}", fg="yellow"))
        else:
            logger.info(style(f"No metadata found in {cloudinary.config().cloud_name}", fg="yellow"))

    upload_list = []
    for r in source_assets.get('resources'):
        updated_options, asset_url = process_metadata(r, overwrite, async_, notification_url,
                                                      normalize_list_params(fields))
        updated_options.update(config_to_dict(target_config))
        upload_list.append((asset_url, {**updated_options}))
    if not upload_list:
        logger.error(style(f"No assets found in {cloudinary.config().cloud_name}", fg="red"))
        return False

    logger.info(style(f"Copying {len(upload_list)} asset(s) from {cloudinary.config().cloud_name} to {target_config.cloud_name}", fg="blue"))

    run_tasks_concurrently(upload_file, upload_list, concurrent_workers)

    return True


def search_assets(force, search_exp):
    search = cloudinary.search.Search().expression(search_exp)
    search.fields(['tags', 'context', 'access_control', 'secure_url', 'display_name','metadata'])
    search.max_results(DEFAULT_MAX_RESULTS)

    res = execute_single_request(search, fields_to_keep="")
    res = handle_auto_pagination(res, search, force, fields_to_keep="")

    return res


def list_metadata_items(method_key, *options):
    api_method_name = 'list_' + method_key
    params = [api_method_name]
    if options:
        options = options[0]
    res = handle_api_command(params, (), options, None, None, None,
                             doc_url="", api_instance=cloudinary.api,
                             api_name="admin",
                             auto_paginate=True,
                             force=True, return_data=True)
    res.get(method_key, []).sort(key=lambda x: x["external_id"])
    
    return res


def create_metadata_item(api_method_name, item, *options):
    params = (api_method_name, item)
    if options:
        options = options[0]
    res = handle_api_command(params, (), options, None, None, None,
                             doc_url="", api_instance=cloudinary.api,
                             api_name="admin",
                             return_data=True)
    
    return res


def deep_diff(obj_source, obj_target):
    diffs = {}
    for k in set(obj_source.keys()).union(obj_target.keys()):
        if obj_source.get(k) != obj_target.get(k):
            diffs[k] = {"json_source": obj_source.get(k), "json_target": obj_target.get(k)}
    
    return diffs


def compare_create_metadata_items(json_source, json_target, target_config, key, id_field = "external_id"):
    list_source = {item[id_field]: item for item in json_source.get(key, [])}
    list_target = {item[id_field]: item for item in json_target.get(key, [])}

    only_in_source = list(list_source.keys() - list_target.keys())
    common = list_source.keys() & list_target.keys()

    if not len(only_in_source):
        logger.info(style(f"{(' '.join(key.split('_')))} in {dict(target_config)['cloud_name']} and in {cloudinary.config().cloud_name} are identical. No {(' '.join(key.split('_')))} will be cloned", fg="yellow"))
    else:
        logger.info(style(f"Copying {len(only_in_source)} {(' '.join(key.split('_')))} from {cloudinary.config().cloud_name} to {dict(target_config)['cloud_name']}", fg="blue"))
    
        for key_field in only_in_source:
            if key == 'metadata_fields':
                try:
                    res = create_metadata_item('add_metadata_field', list_source[key_field],target_config)
                    logger.info(style(f"Successfully created {(' '.join(key.split('_')))} {key_field} to {dict(target_config)['cloud_name']}", fg="green"))
                except Exception as e:
                    logger.error(style(f"Error when creating {(' '.join(key.split('_')))} {key_field} to {dict(target_config)['cloud_name']}", fg="red"))
            else:
                try:
                    res = create_metadata_item('add_metadata_rule', list_source[key_field],target_config)
                    logger.info(style(f"Successfully created {(' '.join(key.split('_')))} {key_field} to {dict(target_config)['cloud_name']}", fg="green"))
                except Exception as e:
                    logger.error(style(f"Error when creating {(' '.join(key.split('_')))} {key_field} to {dict(target_config)['cloud_name']}", fg="red"))
            

    diffs = {}
    for id_ in common:
        if list_source[id_] != list_target[id_]:
            diffs[id_] = deep_diff(list_source[id_], list_target[id_])

    return {
        "only_in_json_source": only_in_source,
        "differences": diffs
    }

    
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
    if "metadata" in copy_fields:
        cloned_options['metadata'] = res.get('metadata')
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
