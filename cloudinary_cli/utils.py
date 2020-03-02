#!/usr/bin/env python3

import json
import os
from hashlib import md5
from inspect import signature, getfullargspec

import cloudinary
from jinja2 import Environment, FileSystemLoader
from pkg_resources import resource_filename
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer
from .defaults import CLOUDINARY_HOME, OLD_CLOUDINARY_CLI_CONFIG_FILE, CLOUDINARY_CLI_CONFIG_FILE, logger

not_callable = ['is_appengine_sandbox', 'call_tags_api', 'call_context_api', 'call_cacheable_api', 'call_api', 'text']


def write_out(contents, filename):
    open(filename, "w+").write(dumps(contents, indent=2))


# def enable_file_logging():
    # fileHandler = logging.FileHandler(abspath(path_join(CLOUDINARY_HOME, "{}.log_json".format(datetime.datetime.now()))))
    # logger.addHandler(fileHandler)


def etag(fi):
    return md5(open(fi, 'rb').read()).hexdigest()


def refresh_config(config):
    os.environ.update(dict(CLOUDINARY_URL=config))
    cloudinary.reset_config()


def initialize():
    if not os.path.isdir(CLOUDINARY_HOME):
        os.mkdir(CLOUDINARY_HOME)

    if not os.path.exists(CLOUDINARY_CLI_CONFIG_FILE):
        open(CLOUDINARY_CLI_CONFIG_FILE, "a").close()

    if not os.path.isdir(CUSTOM_TEMPLATE_FOLDER):
        os.mkdir(CUSTOM_TEMPLATE_FOLDER)
    # migrate old config file to new location
    if os.path.exists(OLD_CLOUDINARY_CLI_CONFIG_FILE):
        with open(OLD_CLOUDINARY_CLI_CONFIG_FILE) as f:
            try:
                old_config = json.loads(f.read())
            except Exception as e:
                raise json.JSONDecodeError("Unable to parse old Cloudinary config file")

        with open(CLOUDINARY_CLI_CONFIG_FILE) as f:
            try:
                new_config = json.loads(f.read())
            except Exception as e:
                raise json.JSONDecodeError("Unable to parse Cloudinary config file")
        new_config.update(old_config)
        with open(CLOUDINARY_CLI_CONFIG_FILE, 'w') as cfg:
            json.dump(new_config, cfg)
        os.remove(OLD_CLOUDINARY_CLI_CONFIG_FILE)
    if os.environ.get("CLOUDINARY_URL") == '':
        logger.warn("CLOUDINARY_URL is not set in your environment. Please set it up in your terminal config file.\n")
        pass


def get_help(api):
    funcs = list(filter(lambda x: callable(api.__dict__[x]) and x[0].islower() and x not in not_callable,
                        api.__dict__.keys()))
    sigs = '\n'.join(["{0:25}({1})".format(x, ", ".join(list(signature(api.__dict__[x]).parameters))) for x in funcs])
    return sigs


def log_json(res):
    try:
        res = json.dumps(res, indent=2)
    finally:
        pass
    colorful_json = highlight(res.encode('UTF-8'), JsonLexer(), TerminalFormatter())
    logger.info(colorful_json)


def load_template(language, _template):
    filepath = resource_filename(__name__, '/'.join([TEMPLATE_FOLDER, language, _template]))
    with open(filepath) as f:
        template = Environment(
            loader=FileSystemLoader(resource_filename(__name__, TEMPLATE_FOLDER))).from_string(f.read())
    return template.render(**cloudinary.config().__dict__)


def parse_option_value(value):
    if value == "True" or value == "true":
        return True
    elif value == "False" or value == "false":
        return False
    try:
        value = json.loads(value)
    except:
        pass
    if isinstance(value, int):
        value = str(value)
    return value


def parse_args_kwargs(func, params):
    spec = getfullargspec(func)
    n_args = len(spec.args) if spec.args else 0
    n_defaults = len(spec.defaults) if spec.defaults else 0

    l = n_args - n_defaults
    if len(params) < l:
        raise Exception("Function '{}' requires {} arguments".format(func.__name__, l))
    args = [parse_option_value(x) for x in params[:l]]

    kwargs = {k: parse_option_value(v) for k, v in [x.split('=') for x in params[l:]]} if params[l:] else {}
    return args, kwargs
