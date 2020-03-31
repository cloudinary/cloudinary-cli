#!/usr/bin/env python3

import json
import os
from csv import DictWriter
from functools import reduce
from hashlib import md5
from inspect import signature, getfullargspec
from multiprocessing import pool

import cloudinary
from jinja2 import Environment

from cloudinary_cli.defaults import logger, TEMPLATE_FOLDER

not_callable = ['is_appengine_sandbox', 'call_tags_api', 'call_context_api', 'call_cacheable_api', 'call_api', 'text']

BLOCK_SIZE = 65536


def etag(fi):
    file_hash = md5()
    with open(fi, 'rb') as f:
        fb = f.read(BLOCK_SIZE)
        while len(fb) > 0:
            file_hash.update(fb)
            fb = f.read(BLOCK_SIZE)

    return file_hash.hexdigest()


def get_help_str(api):
    funcs = list(filter(lambda x: callable(api.__dict__[x]) and x[0].islower() and x not in not_callable,
                        api.__dict__.keys()))
    return '\n'.join(["{0:25}({1})".format(x, ", ".join(list(signature(api.__dict__[x]).parameters))) for x in funcs])


def print_help(api):
    logger.info(get_help_str(api))


def log_exception(e, message=None):
    message = f"{message}, error: {str(e)}" if message is not None else str(e)
    logger.debug(message, exc_info=True)
    logger.error(message)


def load_template(language, template_name):
    filepath = os.path.join(TEMPLATE_FOLDER, language, template_name)
    try:
        with open(filepath) as f:
            template = Environment().from_string(f.read())
    except IOError:
        logger.error(f"Failed loading template: '{template_name}' for language: '{language}'")
        raise
    return template.render(**cloudinary.config().__dict__)


def parse_option_value(value):
    if value == "True" or value == "true":
        return True
    elif value == "False" or value == "false":
        return False
    try:
        value = json.loads(value)
    except Exception:
        pass
    if isinstance(value, int):
        value = str(value)
    return value


def parse_args_kwargs(func, params):
    spec = getfullargspec(func)
    n_args = len(spec.args) if spec.args else 0
    n_defaults = len(spec.defaults) if spec.defaults else 0

    n_req = n_args - n_defaults
    if len(params) < n_req:
        raise Exception("Function '{}' requires {} arguments".format(func.__name__, n_req))
    args = [parse_option_value(x) for x in params[:n_req]]

    kwargs = {k: parse_option_value(v) for k, v in [x.split('=') for x in params[n_req:]]} if params[n_req:] else {}
    return args, kwargs


def remove_string_prefix(string, prefix):
    return string[string.startswith(prefix) and len(prefix):]


def write_json_list_to_csv(json_list, filename, fields_to_keep=()):
    with open(f'{filename}.csv', 'w') as f:
        if not fields_to_keep:
            fields_to_keep = list(reduce(lambda x, y: set(y.keys()) | x, json_list, set()))

        writer = DictWriter(f, fieldnames=fields_to_keep)
        writer.writeheader()
        writer.writerows(json_list)


def run_tasks_concurrently(func, tasks, concurrent_workers):
    thread_pool = pool.ThreadPool(concurrent_workers)
    thread_pool.starmap(func, tasks)


def confirm_action(message):
    r = input(message)
    if r.lower() != 'y':
        return False

    return True
