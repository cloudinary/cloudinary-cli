import logging
from os import path, makedirs
from webbrowser import open as open_url

import requests
from click import style
from cloudinary import Search, uploader
from cloudinary.utils import cloudinary_url

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.json_utils import print_json, write_json_to_file
from cloudinary_cli.utils.utils import print_help, parse_args_kwargs, parse_option_value, log_exception


def query_cld_folder(folder):
    files = {}
    next_cursor = True
    expression = Search().expression(f"folder:{folder}/*").with_field("image_analysis").max_results(500)
    while next_cursor:
        res = expression.execute()

        for asset in res['resources']:
            rel_path = path.relpath(asset['public_id'], folder)
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
    uploaded = uploaded if uploaded is not None else []
    skipped = skipped if skipped is not None else []
    verbose = logger.getEffectiveLevel() < logging.INFO

    try:
        result = uploader.upload(file_path, **options)
        logger.info(style(f"Successfully uploaded {file_path} as {result['public_id']}", fg="green"))
        if verbose:
            print_json(result)
        uploaded.append(result['public_id'])
    except Exception as e:
        log_exception(e, f"Failed uploading {file_path}")
        skipped.append(file_path)
        raise


def download_file(remote_file, local_path):
    makedirs(path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(requests.get(cloudinary_url(remote_file['public_id'], resource_type=remote_file['resource_type'],
                                            type=remote_file['type'])[0]).content)
    logger.info(style("Downloaded '{}' to '{}'".format(remote_file['relative_path'], local_path), fg="green"))


def handle_api_command(
        params,
        optional_parameter,
        optional_parameter_parsed,
        ls,
        save,
        doc,
        doc_url,
        api_instance,
        api_name):
    """
    Used by Admin and Upload API commands
    """
    if doc:
        return open_url(doc_url)

    if ls or len(params) < 1:
        return print_help(api_instance)

    try:
        func = api_instance.__dict__[params[0]]
        if not callable(func):
            raise Exception(f"{func} is not callable")
    except Exception:
        raise Exception(f"Method {params[0]} does not exist in the {api_name.capitalize()} API.")

    args, kwargs = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})

    res = func(*args, **{
        **kwargs,
        **{k: v for k, v in optional_parameter},
        **{k: parse_option_value(v) for k, v in optional_parameter_parsed},
    })

    print_json(res)

    if save:
        write_json_to_file(res, save)
