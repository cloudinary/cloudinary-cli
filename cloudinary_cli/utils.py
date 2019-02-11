#!/usr/bin/env python3

from jinja2 import Template, Environment, FileSystemLoader
from pygments import highlight, lexers, formatters
from inspect import signature
from json import loads, dumps
from subprocess import Popen
import os
import cloudinary
import re

TEMPLATE_FOLDER = "cloudinary_cli/templates"

TEMPLATE_EXTS = {
    "python": "py",
    "html": "html",
    "ruby": "rb",
    "node": "js",
    "php": "php",
    "java": "java",
}

def get_sample(which, transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url(which, raw_transformation=transformation)[0]
    return res

def get_help(api):
    funcs = list(filter(lambda x: callable(api.__dict__[x]) and x[0].islower(), api.__dict__.keys()))
    sigs = '\n'.join(["{0:25}({1})".format(x, ", ".join(list(signature(api.__dict__[x]).parameters))) for x in funcs])
    return sigs

def log(res):
    try:
        res = dumps(dict(res), indent=2)
    except:
        pass
    colorful_json = highlight(res.encode('UTF-8'), lexers.JsonLexer(), formatters.TerminalFormatter())
    print(colorful_json)

def load_template(language, _template):
    with open(os.path.join(TEMPLATE_FOLDER, language, _template)) as f:
        template = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER)).from_string(f.read())
    return template.render(**cloudinary._config.__dict__)

def parse_option_value(value):
    valid = re.match('^[\w-]+$', value) is not None
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
    args = [parse_option_value(x) for x in params[:l]]
    kwargs = {k: parse_option_value(v) for k,v in [x.split('=') for x in params[l:]]} if params[l:] else {}
    return args, kwargs

def open_url(url):
    Popen(["open", url])
