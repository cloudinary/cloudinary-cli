from jinja2 import Template, Environment, FileSystemLoader
from pygments import highlight, lexers, formatters
from inspect import signature
from json import loads, dumps
from subprocess import Popen
from os import getcwd
import os
import cloudinary
import re

TEMPLATE_FOLDER = os.path.join(os.path.abspath(__file__), "../templates")

TEMPLATE_EXTS = {
    "python": "py",
    "html": "html",
    "ruby": "rb",
    "node": "js",
    "php": "php",
    "java": "java",
}

def log(res):
    try:
        res = dumps(dict(res), indent=2)
    except:
        pass
    colorful_json = highlight(res.encode('UTF-8'), lexers.JsonLexer(), formatters.TerminalFormatter())
    print(colorful_json)

def load_template(language, _template):
    with open(os.path.abspath(os.path.join(TEMPLATE_FOLDER, language, _template))) as f:
        template = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER)).from_string(f.read())
    return template.render(**cloudinary._config.__dict__)

def parse_option_value(value):
    try:
        value = loads(value)
    except:
        valid = re.match('^[\w-]+$', value) is not None
        if valid:
            with value.lower() as val_:
                if val_ == "true":
                    value = True
                elif val_ == "false":
                    value = False
        pass
    return value

def parse_args_kwargs(func, params):
    p = signature(func)
    l = len(p.parameters) - 1
    args = params[:l]
    kwargs = {k: parse_option_value(v) for k,v in [x.split('=') for x in params[l:]]} if params[l:] else {}
    return args, kwargs

def open_url(url):
    Popen(["open", url])
