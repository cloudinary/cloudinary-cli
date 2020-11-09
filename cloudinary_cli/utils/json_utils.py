import json
from platform import system
from os import path
import click
from pygments import highlight, lexers, formatters


def read_json_from_file(filename, does_not_exist_ok=False):
    if does_not_exist_ok and (not path.exists(filename) or path.getsize(filename) < 1):
        return {}

    with open(filename, 'r') as file:
        return json.loads(file.read() or "{}")


def write_json_to_file(json_obj, filename, indent=2, sort_keys=False):
    with open(filename, 'w') as file:
        json.dump(json_obj, file, indent=indent, sort_keys=sort_keys)


def update_json_file(json_obj, filename, indent=2, sort_keys=False):
    curr_obj = read_json_from_file(filename, True)
    curr_obj.update(json_obj)
    write_json_to_file(curr_obj, filename, indent, sort_keys)


def print_json(res):
    res_str = json.dumps(res, indent=2)

    if system() != "Windows":
        res_str = highlight(res_str.encode('UTF-8'), lexers.JsonLexer(), formatters.TerminalFormatter()).strip()

    click.echo(res_str)
