#!/usr/bin/env python3
import builtins
import json
import os
from collections import OrderedDict
from csv import DictWriter
from functools import reduce
from hashlib import md5
from inspect import signature, getfullargspec
from typing import get_type_hints
from multiprocessing import pool

import click
import cloudinary
from jinja2 import Environment, FileSystemLoader
from docstring_parser import parse
from cloudinary_cli.defaults import logger, TEMPLATE_FOLDER
from cloudinary.utils import build_array

not_callable = ('is_appengine_sandbox', 'call_tags_api', 'call_context_api', 'call_cacheable_api', 'call_api',
                'call_metadata_api', 'call_json_api', 'only', 'transformation_string', 'account_config',
                'reset_config', 'upload_large_part', 'upload_image', 'upload_resource', 'build_eager')

BLOCK_SIZE = 65536


class ConfigurationError(Exception):
    pass


def etag(fi):
    file_hash = md5()
    with open(fi, 'rb') as f:
        fb = f.read(BLOCK_SIZE)
        while len(fb) > 0:
            file_hash.update(fb)
            fb = f.read(BLOCK_SIZE)

    return file_hash.hexdigest()


def is_builtin_class_instance(obj):
    return type(obj).__name__ in dir(builtins)


def get_help_str(module, block_list=(), allow_list=()):
    funcs = {}
    for f in module.__dict__.keys():
        if callable(module.__dict__[f]) \
                and not is_builtin_class_instance(module.__dict__[f]) \
                and f[0].islower() \
                and (f not in block_list and block_list) \
                and (f in allow_list or not allow_list):
            funcs[f] = {"params": ", ".join(signature(module.__dict__[f]).parameters),
                        "desc": parse(module.__dict__[f].__doc__).short_description}

    funcs = OrderedDict(sorted(funcs.items()))

    # Gets the max length of the functions' names
    template = "{0:" + str(len(max(funcs.keys(), key=len)) + 1) + "}({1:30} {2}"

    return '\n'.join(
        [
            template.format(f, p["params"] + ")", p["desc"] if p["desc"] is not None else "")
            for f, p in funcs.items()
        ])


def print_api_help(api, block_list=not_callable, allow_list=()):
    logger.info(get_help_str(api, block_list=block_list, allow_list=allow_list))


def log_exception(e, message=None, debug_message=None):
    message = f"{message}, error: {str(e)}" if message is not None else str(e)
    debug_message = debug_message or message
    logger.debug(debug_message, exc_info=True)
    logger.error(message)


def load_template(language, template_name):
    filepath = os.path.join(TEMPLATE_FOLDER, language, template_name)
    if not os.path.exists(filepath):
        logger.error(f"Template: '{template_name}' for language: '{language}' does not exist")
        return False
    try:
        with open(filepath) as f:
            template = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER)).from_string(f.read())
    except IOError:
        logger.error(f"Failed loading template: '{template_name}' for language: '{language}'")
        raise
    try:
        result = template.render(**cloudinary.config().__dict__)
    except Exception:
        logger.error(f"Failed rendering template: '{template_name}' for language: '{language}'")
        raise

    return result


def parse_option_value(value):
    if isinstance(value, list):
        return list(map(parse_option_value, value))

    if value == "True" or value == "true":
        return True
    elif value == "False" or value == "false":
        return False
    try:
        value = json.loads(value)
    except Exception:
        pass
    # serialize 0 to "0" string, otherwise it will be omitted (counted as False)
    if isinstance(value, int) and not value:
        value = str(value)
    return value


def parse_args_kwargs(func, params=None, kwargs=None):
    if params is None:
        params = []
    if kwargs is None:
        kwargs = {}

    spec = getfullargspec(func)

    num_args = len(spec.args) if spec.args else 0
    num_defaults = len(spec.defaults) if spec.defaults else 0

    num_req = num_args - num_defaults
    num_provided_args = len(params)
    num_overall_provided = num_provided_args + len([p for p in kwargs.keys() if p in spec.args[num_provided_args:]])

    if num_overall_provided < num_req:
        func_sig = signature(func)
        raise Exception(f"Function '{func.__name__}{func_sig}' requires {num_req} positional arguments")

    # consume required args
    args = [parse_option_value(p) for p in params[:num_req]]

    for p in params[num_req:]:
        if '=' not in p:
            # named/positional with default value args passed as positional
            args.append(parse_option_value(p))
            continue

        k, v = p.split('=', 1)
        kwargs[k] = parse_option_value(v)

    params_specs = parse(func.__doc__).params

    if len(args) > num_req:
        # Here we consumed more args than the function can get,
        # let's see if we have a list arg and pass everything as list.
        # Otherwise, let's pass everything as is and hope for the best :)
        last_positional_list_param = next((s for s in reversed(params_specs) if s.arg_name not in kwargs and s.type_name and s.type_name.startswith('list')), None)
        if last_positional_list_param:
            pos = get_index_by_name(spec.args, last_positional_list_param.arg_name)
            args[pos] = [args[pos]] + args[num_args:]
            args = args[:num_args]

    for s in params_specs:
        if s.type_name and s.type_name.startswith('list'):
            pos = get_index_by_name(spec.args, s.arg_name)
            if isinstance(pos, int) and 0 <= pos < len(args):
                args[pos] = normalize_list_params(args[pos])
            if s.arg_name in kwargs:
                kwargs[s.arg_name] = normalize_list_params(kwargs[s.arg_name])

    return args, kwargs

def get_index_by_name(lst, name):
    return next((i for i, item in enumerate(lst) if item == name), -1)

def remove_string_prefix(string, prefix):
    return string[string.startswith(prefix) and len(prefix):]


def invert_dict(d):
    inv_dict = {}
    for k, v in d.items():
        inv_dict[v] = k

    return inv_dict


def write_json_list_to_csv(json_list, filename, fields_to_keep=()):
    with open(f'{filename}.csv', 'w') as f:
        if not fields_to_keep:
            fields_to_keep = list(reduce(lambda x, y: set(y.keys()) | x, json_list, set()))

        writer = DictWriter(f, fieldnames=fields_to_keep)
        writer.writeheader()
        writer.writerows(json_list)


def run_tasks_concurrently(func, tasks, concurrent_workers):
    with pool.ThreadPool(concurrent_workers) as thread_pool:
        thread_pool.starmap(func, tasks)


def confirm_action(message="Continue? (y/N)"):
    """
    Confirms whether the user wants to continue.

    :param message: The message to the user.
    :type message: string

    :return: Boolean indicating whether user wants to continue.
    :rtype bool
    """
    return get_user_action(message, {"y": True, "default": False})


def get_user_action(message, options):
    """
    Reads user input and returns value specified in options.

    In case user specified unknown option, returns default value.
    If default value is not set, returns None

    :param message: The message for user.
    :type message: string
    :param options: Options mapping.
    :type options: dict

    :return: Value according to the user selection.
    """
    r = input(message).lower()
    return options.get(r, options.get("default"))


def get_command_params(
        params,
        optional_parameter,
        optional_parameter_parsed,
        module,
        module_name):
    method = params[0]
    if method not in module.__dict__:
        raise Exception(f"Method {params[0]} does not exist in {module_name.capitalize()}.")

    func = module.__dict__.get(method)

    if not callable(func):
        raise Exception(f"{params[0]} is not callable.")

    kwargs = group_params(optional_parameter, ((k, parse_option_value(v)) for k, v in optional_parameter_parsed))

    args, kwargs = parse_args_kwargs(func, params[1:], kwargs)

    return func, args, kwargs


def group_params(*params):
    """
    Groups parameters (which are passed as list of tuples) by keys. Duplicate keys' values are combined into lists.

    :param params: the list of parameters to group
    :return: dict
    """
    res = {}
    for param in params:
        for k, v in param:
            if k in res:
                res[k] = (res[k] if isinstance(res[k], list) else [res[k]]) + [v]
                continue
            res[k] = v

    return res


def print_help_and_exit():
    """
    Prints help for the current command and exits.
    """
    ctx = click.get_current_context()
    click.echo(ctx.get_help())
    ctx.exit()


def whitelist_keys(data, keys):
    """
    Iterates over a list of dictionaries and keeps only the keys that were specified.

    :param data: A list of dictionaries.
    :type data: list
    :param keys: a list of keys to keep in each dictionary.
    :type keys: list

    :return: The whitelisted list.
    :rtype list
    """
    # no whitelist when fields are not provided or on a list of non-dictionary items.
    if not keys or any(not isinstance(i, dict) for i in data):
        return data

    return list(
        map(lambda x: {
            k: x[k]
            for k in keys if k in x},
            data)
    )


def merge_responses(all_res, paginated_res, fields_to_keep=None, pagination_field=None):
    if not pagination_field:
        for key in all_res:
            if all_res[key] != paginated_res.get(key, 0) and type(all_res[key]) == list:
                pagination_field = key

        if not pagination_field:  # should not happen
            raise Exception("Failed to detect pagination_field")

        # whitelist fields of the initial response
        all_res[pagination_field] = whitelist_keys(all_res[pagination_field], fields_to_keep)

    all_res[pagination_field] += whitelist_keys(paginated_res[pagination_field], fields_to_keep)

    return all_res, pagination_field


def normalize_list_params(params):
    """
    Normalizes parameters that could be provided as strings separated by ','.

    >>> normalize_list_params(['f1,f2', 'f3'])
    ['f1', 'f2', 'f3']

    >>> normalize_list_params('f1,f2,f3')
    ['f1', 'f2', 'f3']

    :param params: Params to normalize.
    :type params: list[string] or string

    :return: A list of normalized params.
    :rtype list
    """
    normalized_params = []
    for f in build_array(params):
        if isinstance(f, str) and "," in f:
            normalized_params += f.split(",")
        else:
            normalized_params.append(f)

    return normalized_params


def chunker(seq, size):
    """
    Iterates a sequence in chunks of a given size.

    >>> for group in chunker(['cat', 'dog', 'rabbit', 'duck', 'bird', 'cow', 'gnu', 'fish'], 3):
    >>>    print(group)

    Produces:

    ['cat', 'dog', 'rabbit']
    ['duck', 'bird', 'cow']
    ['gnu', 'fish']

    :param seq: The sequence to iterate.
    :param size: The size of a single chunk.
    :return: a single chunk
    """
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def duplicate_values(items, value_key, key_of_interest=None):
    """
    Finds duplicate values in a dictionary of objects.

    :param items: All items.
    :param value_key: The duplicate value key to search.
    :param key_of_interest: The key to add to the resulting list.
    :return:
    """
    rev_multidict = {}
    for key, value in items.items():
        rev_multidict.setdefault(value[value_key], set()).add(value[key_of_interest] if key_of_interest is not None else key)

    return {key: values for key, values in rev_multidict.items() if len(values) > 1}


def split_opt(opt):
    """
    Splits an option string into prefix and value parts.

    This function replaces the deprecated click.parser.split_opt import.
    Returns a tuple of (prefix, value) where prefix is the option prefix
    (like '-' or '--') and value is the remaining part, or ('', opt)
    if it doesn't look like an option.

    :param opt: The option string to parse.
    :type opt: str
    :return: Tuple of (prefix, value)
    :rtype: tuple
    """
    first = opt[:1]
    if first.isalnum():
        return '', opt
    if opt[1:2] == first:
        return opt[:2], opt[2:]
    return first, opt[1:]
