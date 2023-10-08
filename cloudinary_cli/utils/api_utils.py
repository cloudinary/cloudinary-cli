import logging
from os import path, makedirs

import requests
from click import style, launch
from cloudinary import Search, uploader, api
from cloudinary.utils import cloudinary_url

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import is_valid_cloudinary_config
from cloudinary_cli.utils.file_utils import normalize_file_extension, posix_rel_path, get_destination_folder
from cloudinary_cli.utils.json_utils import print_json, write_json_to_file
from cloudinary_cli.utils.utils import log_exception, confirm_action, get_command_params, merge_responses, \
    normalize_list_params, ConfigurationError, print_api_help

PAGINATION_MAX_RESULTS = 500

_cursor_fields = {"resource": "derived_next_cursor"}


def query_cld_folder(folder, folder_mode):
    files = {}

    folder = folder.strip('/')  # omit redundant leading slash and duplicate trailing slashes in query
    folder_query = f"{folder}/*" if folder else "*"

    expression = Search().expression(f"folder:\"{folder_query}\"").with_field("image_analysis").max_results(500)

    next_cursor = True
    while next_cursor:
        res = expression.execute()

        for asset in res['resources']:
            rel_path = _relative_path(asset, folder)
            rel_display_path = _relative_display_path(asset, folder)
            path_key = rel_display_path if folder_mode == "dynamic" else rel_path
            files[normalize_file_extension(path_key)] = {
                "type": asset['type'],
                "resource_type": asset['resource_type'],
                "public_id": asset['public_id'],
                "format": asset['format'],
                "etag": asset.get('etag', '0'),
                "relative_path": rel_path,  # save for inner use
                "access_mode": asset.get('access_mode', 'public'),
                # dynamic folder mode fields
                "asset_folder": asset.get('asset_folder'),
                "display_name": asset.get('display_name'),
                "relative_display_path": rel_display_path
            }
        # use := when switch to python 3.8
        next_cursor = res.get('next_cursor')
        expression.next_cursor(next_cursor)

    return files


def _display_path(asset):
    if asset.get("display_name") is None:
        return ""

    return "/".join([asset.get("asset_folder", ""), ".".join([asset["display_name"], asset["format"]])])


def _relative_display_path(asset, folder):
    if asset.get("display_name") is None:
        return ""

    return posix_rel_path(_display_path(asset), folder)


def _relative_path(asset, folder):
    source = asset_source(asset)
    if not source.startswith(folder):
        return source

    return posix_rel_path(asset_source(asset), folder)


def regen_derived_version(public_id, delivery_type, res_type,
                          eager_trans, eager_async,
                          eager_notification_url):
    options = {"type": delivery_type, "resource_type": res_type,
                "eager": eager_trans, "eager_async": eager_async,
                "eager_notification_url": eager_notification_url,
                "overwrite": True, "invalidate": True}
    try:
        exp_res = uploader.explicit(public_id, **options)
        derived_url = f'{exp_res.get("eager")[0].get("secure_url")}'
        msg = ('Processing' if options.get('eager_async') else 'Regenerated') + f' {derived_url}'
        logger.info(style(msg, fg="green"))
    except Exception as e:
        error_msg = (f"Failed to regenerate {public_id} of type: "
                     f"{options.get('type')} and resource_type: "
                     f"{options.get('resource_type')}")
        log_exception(e, error_msg)


def upload_file(file_path, options, uploaded=None, failed=None):
    uploaded = uploaded if uploaded is not None else {}
    failed = failed if failed is not None else {}
    verbose = logger.getEffectiveLevel() < logging.INFO

    try:
        size = path.getsize(file_path)
        upload_func = uploader.upload
        if size > 20000000:
            upload_func = uploader.upload_large
        result = upload_func(file_path, **options)
        disp_path = _display_path(result)
        disp_str = f"as {result['public_id']}" if not disp_path \
            else f"as {disp_path} with public_id: {result['public_id']}"
        logger.info(style(f"Successfully uploaded {file_path} {disp_str}", fg="green"))
        if verbose:
            print_json(result)
        uploaded[file_path] = {"path": asset_source(result), "display_path": disp_path}
    except Exception as e:
        log_exception(e, f"Failed uploading {file_path}")
        failed[file_path] = str(e)


def get_default_upload_options(folder_mode):
    options = {
        'resource_type': 'auto'
    }

    if folder_mode == 'fixed':
        options = {
            **options,
            'use_filename': True,
            'unique_filename': False,
            'invalidate': True,
        }

    if folder_mode == 'dynamic':
        options = {
            **options,
            'use_filename_as_display_name': True,
        }

    return options


def get_destination_folder_options(file, remote_dir, folder_mode, parent=None):
    destination_folder = get_destination_folder(remote_dir, file, parent)

    if folder_mode == "dynamic":
        return {"asset_folder": destination_folder}

    return {"folder": destination_folder}


def download_file(remote_file, local_path, downloaded=None, failed=None):
    downloaded = downloaded if downloaded is not None else {}
    failed = failed if failed is not None else {}
    makedirs(path.dirname(local_path), exist_ok=True)

    if remote_file['type'] in ("private", "authenticated") or remote_file['access_mode'] == "authenticated":
        sign_url = True
    else:
        sign_url = False

    download_url = cloudinary_url(asset_source(remote_file), resource_type=remote_file['resource_type'],
                                  type=remote_file['type'], sign_url=sign_url)[0]

    result = requests.get(download_url)

    if result.status_code != 200:
        err = result.headers.get('x-cld-error')
        msg = f"Failed downloading: {download_url}, status code: {result.status_code}, " \
              f"details: {err}"
        logger.error(msg)
        failed[download_url] = err
        return

    with open(local_path, "wb") as f:
        f.write(result.content)

    downloaded[remote_file['relative_path']] = local_path

    logger.info(style("Downloaded '{}' to '{}'".format(remote_file['relative_path'], local_path), fg="green"))


def asset_source(asset_details):
    """
    Public ID of the transformable file (image/video) does not include file extension.

    It needs to be added in order to download the file properly (without creating a derived asset).

    Raw files are accessed using only public_id.

    Fetched files are not altered as well.

    :param asset_details: The details of the asset.
    :rtype asset_details: dict

    :return:
    """
    base_name = asset_details['public_id']

    if asset_details['resource_type'] == 'raw' or asset_details['type'] == 'fetch':
        return base_name

    return base_name + '.' + asset_details['format']


def get_folder_mode():
    """
    Returns folder mode of the cloud.

    :return: String representing folder mode. Can be "fixed" or "dynamic".
    """
    try:
        config_res = api.config(settings="true")
        mode = config_res["settings"]["folder_mode"]
        logger.debug(f"Using {mode} folder mode")
    except Exception as e:
        log_exception(e, f"Failed getting cloud configuration")
        raise

    return mode


def call_api(func, args, kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        log_exception(e, f"Failed calling '{func.__name__}' with args: {args} and optional args {kwargs}")
        raise


def handle_command(
        params,
        optional_parameter,
        optional_parameter_parsed,
        module,
        module_name):
    try:
        func, args, kwargs = get_command_params(params, optional_parameter, optional_parameter_parsed, module,
                                                module_name)
    except Exception as e:
        log_exception(e)
        return False

    return call_api(func, args, kwargs)


def handle_api_command(
        params,
        optional_parameter,
        optional_parameter_parsed,
        ls,
        save,
        doc,
        doc_url,
        api_instance,
        api_name,
        auto_paginate=False,
        force=False,
        filter_fields=None,
        return_data=False):
    """
    Used by Admin and Upload API commands
    """

    if doc:
        return launch(doc_url)

    if ls or len(params) < 1:
        return print_api_help(api_instance)

    try:
        func, args, kwargs = get_command_params(params, optional_parameter, optional_parameter_parsed, api_instance,
                                                api_name)
    except Exception as e:
        log_exception(e)
        return False

    if not is_valid_cloudinary_config():
        raise ConfigurationError("No Cloudinary configuration found.")

    try:
        res = call_api(func, args, kwargs)
    except Exception:
        return False

    if auto_paginate:
        res = handle_auto_pagination(res, func, args, kwargs, force, filter_fields)

    if return_data:
        return res

    print_json(res)

    if save:
        write_json_to_file(res, save)


def handle_auto_pagination(res, func, args, kwargs, force, filter_fields):
    cursor_field = _cursor_fields.get(func.__name__, "next_cursor")

    if cursor_field not in res:
        return res

    if not force:
        if not confirm_action(
                "Using auto pagination will use multiple API calls.\n" +
                f"You currently have {res.rate_limit_remaining} Admin API calls remaining. Continue? (y/N)"):
            logger.info("Stopping. Please run again without -A.")

            return res
        else:
            logger.info("Continuing. You may use the -F flag to force auto_pagination.")

    fields_to_keep = []
    if filter_fields:
        fields_to_keep = normalize_list_params(filter_fields)

    kwargs['max_results'] = PAGINATION_MAX_RESULTS

    all_results = res
    # We have many different APIs that have different fields that we paginate.
    # The field is unknown before we perform the second call and then compare results and find the field.
    pagination_field = None
    while res.get(cursor_field, None):
        kwargs[cursor_field] = res.get(cursor_field, None)
        res = call_api(func, args, kwargs)
        all_results, pagination_field = merge_responses(all_results, res, fields_to_keep=fields_to_keep,
                                                        pagination_field=pagination_field)

    all_results.pop(cursor_field, None)

    return all_results
