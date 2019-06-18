#!/usr/bin/env python3

from jinja2 import Template, Environment, FileSystemLoader
from pygments import highlight, lexers, formatters
from pygments.lexers import JsonLexer, JsonBareObjectLexer
from pygments.formatters import TerminalFormatter
from inspect import signature
from json import loads, dumps
from cloudinary import utils
import cloudinary
from pkg_resources import resource_filename
from .defaults import *

F_FAIL = lambda x: "\033[91m" + x + "\033[0m"
F_WARN = lambda x: "\033[93m" + x + "\033[0m"
F_OK = lambda x: "\033[92m" + x + "\033[0m"

write_out = lambda contents, filename: open(filename, "w+").write(dumps(contents, indent=2))

def get_sample(which, transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url(which, raw_transformation=transformation)[0]
    return res


not_callable = ['is_appengine_sandbox', 'call_tags_api', 'call_context_api', 'call_cacheable_api', 'call_api', 'text']

def get_help(api):
    funcs = list(filter(lambda x: callable(api.__dict__[x]) and x[0].islower() and x not in not_callable, api.__dict__.keys()))
    sigs = '\n'.join(["{0:25}({1})".format(x, ", ".join(list(signature(api.__dict__[x]).parameters))) for x in funcs])
    return sigs

def log(res):
    try:
        res = dumps(res, indent=2)
    except:
        pass
    colorful_json = highlight(res.encode('UTF-8'), JsonLexer(), TerminalFormatter())
    print(colorful_json)

def load_template(language, _template):
    filepath = resource_filename(__name__, '/'.join([TEMPLATE_FOLDER, language, _template]))
    with open(filepath) as f:
        template = Environment(loader=FileSystemLoader(resource_filename(__name__, TEMPLATE_FOLDER))).from_string(f.read())
    return template.render(**cloudinary._config.__dict__)

def parse_option_value(value):
    if value == "True" or value == "true":
        return True
    elif value == "False" or value == "false":
        return False
    try:
        value = loads(value)
    except:
        pass
    return value

def parse_args_kwargs(func, params):
    p = signature(func)
    l = len(p.parameters) - 1
    if len(params) < l:
        print("Function '{}' requires {} arguments".format(func.__name__, l))
        exit(1)
    args = [parse_option_value(x) for x in params[:l]]
    kwargs = {k: parse_option_value(v) for k, v in [x.split('=') for x in params[l:]]} if params[l:] else {}
    return args, kwargs
