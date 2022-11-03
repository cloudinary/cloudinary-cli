import logging
from os import path, makedirs

import requests
from click import style, launch
from cloudinary import Search, uploader
from cloudinary.utils import cloudinary_url

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import is_valid_cloudinary_config
from cloudinary_cli.utils.file_utils import normalize_file_extension, posix_rel_path
from cloudinary_cli.utils.json_utils import print_json, write_json_to_file
from cloudinary_cli.utils.utils import log_exception, confirm_action, get_command_params, merge_responses, \
    normalize_list_params, ConfigurationError, print_api_help

PAGINATION_MAX_RESULTS = 500

_cursor_fields = {"resource": "derived_next_cursor"}


def query_cld_folder(folder):
    files = {}

    folder = folder.strip('/')  # omit redundant leading slash and duplicate trailing slashes in query
    folder_query = f"{folder}/*" if folder else "*"

    expression = Search().expression(f"folder:\"{folder_query}\"").with_field("image_analysis").max_results(500)

    next_cursor = True
    while next_cursor:
        res = expression.execute()

        for asset in res['resources']:
            rel_path = posix_rel_path(asset_source(asset), folder)
            files[normalize_file_extension(rel_path)] = {
                "type": asset['type'],
                "resource_type": asset['resource_type'],
                "public_id": asset['public_id'],
                "format": asset['format'],
                "etag": asset.get('etag', '0'),
                "relative_path": rel_path,  # save for inner use
                "access_mode": asset.get('access_mode', 'public'),
            }
        # use := when switch to python 3.8
        next_cursor = res.get('next_cursor')
        expression.next_cursor(next_cursor)

    return files


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
        logger.info(style(f"Successfully uploaded {file_path} as {result['public_id']}", fg="green"))
        if verbose:
            print_json(result)
        uploaded[file_path] = asset_source(result)
    except Exception as e:
        log_exception(e, f"Failed uploading {file_path}")
        failed[file_path] = str(e)


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
        filter_fields=None):
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
