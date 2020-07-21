import logging
from os import path, makedirs
from webbrowser import open as open_url

import requests
from click import style
from cloudinary import Search, uploader
from cloudinary.utils import cloudinary_url

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.json_utils import print_json, write_json_to_file
from cloudinary_cli.utils.utils import print_help, log_exception, confirm_action, only_fields, get_command_params


def query_cld_folder(folder):
    files = {}

    folder = folder.strip('/')  # omit redundant leading slash and duplicate trailing slashes in query
    folder_query = f"{folder}/*" if folder else "*"

    expression = Search().expression(f"folder:\"{folder_query}\"").with_field("image_analysis").max_results(500)

    next_cursor = True
    while next_cursor:
        res = expression.execute()

        for asset in res['resources']:
            rel_path = path.relpath(asset_source(asset), folder)
            files[rel_path] = {
                "type": asset['type'],
                "resource_type": asset['resource_type'],
                "public_id": asset['public_id'],
                "format": asset['format'],
                "etag": asset.get('etag', '0'),
                "relative_path": rel_path,  # save for inner use
            }
        # use := when switch to python 3.8
        next_cursor = res.get('next_cursor')
        expression.next_cursor(next_cursor)

    return files


def upload_file(file_path, options, uploaded=None, skipped=None):
    uploaded = uploaded if uploaded is not None else {}
    skipped = skipped if skipped is not None else []
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
        skipped.append(file_path)
        raise


def download_file(remote_file, local_path):
    makedirs(path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        download_url = cloudinary_url(asset_source(remote_file), resource_type=remote_file['resource_type'],
                                      type=remote_file['type'])[0]
        f.write(requests.get(download_url).content)
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
    return func(*args, **kwargs)


def handle_command(
        params,
        optional_parameter,
        optional_parameter_parsed,
        module,
        module_name):
    func, args, kwargs = get_command_params(params,
                                            optional_parameter,
                                            optional_parameter_parsed,
                                            module,
                                            module_name)
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
        auto_paginate_field=None,
        cursor_field=None,
        filter_fields=None):
    """
    Used by Admin and Upload API commands
    """
    if doc:
        return open_url(doc_url)

    if ls or len(params) < 1:
        return print_help(api_instance)

    func, args, kwargs = get_command_params(
        params,
        optional_parameter,
        optional_parameter_parsed,
        api_instance,
        api_name)

    res = call_api(func, args, kwargs)

    if auto_paginate_field:
        if cursor_field is None:
            raise Exception("Using the `--auto_paginate_field` option requires a `--cursor_field` value.")

        if confirm_action("Using auto pagination will use multiple API calls.\n" +
                          f"You currently have {res.rate_limit_remaining} Admin API calls remaining. Continue? (y/N)"):
            
            fields_to_keep = []
            if filter_fields:
                for f in list(filter_fields):
                    if "," in f:
                        fields_to_keep += f.split(",")
                    
            all_results = res

            all_results[auto_paginate_field] = only_fields(all_results[auto_paginate_field], fields_to_keep)

            kwargs['max_results'] = 500

            while True:
                kwargs[cursor_field] = res[cursor_field]
                res = call_api(func, args, kwargs)
                all_results[auto_paginate_field] += only_fields(res[auto_paginate_field], fields_to_keep)

                if cursor_field not in res.keys():
                    del all_results[cursor_field]
                    break

            res = all_results

    print_json(res)

    if save:
        write_json_to_file(res, save)
