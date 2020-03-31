import json
from platform import system

import click
from pygments import highlight, lexers, formatters


def write_json_to_file(json_obj, filename, indent=2, sort_keys=False):
    with open(filename, 'w') as file:
        json.dump(json_obj, file, indent=indent, sort_keys=sort_keys)


def read_json_from_file(filename):
    with open(filename, 'r') as file:
        return json.loads(file.read() or "{}")


def print_json(res):
    res_str = json.dumps(res, indent=2)

    if system() != "Windows":
        res_str = highlight(res_str.encode('UTF-8'), lexers.JsonLexer(), formatters.TerminalFormatter()).strip()

    click.echo(res_str)
