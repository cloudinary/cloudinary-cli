import json
import sys
from os import path
import click
from pygments import highlight, lexers, formatters

from cloudinary_cli.utils.file_utils import atomic_write


def read_json_from_file(filename, does_not_exist_ok=False):
    if does_not_exist_ok and (not path.exists(filename) or path.getsize(filename) < 1):
        return {}

    with open(filename, 'r') as file:
        return json.loads(file.read() or "{}")


def write_json_to_file(json_obj, filename, indent=2, sort_keys=False, atomic=False, mode=None):
    def dump(file):
        json.dump(json_obj, file, indent=indent, sort_keys=sort_keys)

    if atomic:
        atomic_write(filename, dump, mode=mode)
    else:
        with open(filename, 'w') as file:
            dump(file)


def update_json_file(json_obj, filename, indent=2, sort_keys=False, atomic=False):
    curr_obj = read_json_from_file(filename, True)
    curr_obj.update(json_obj)
    write_json_to_file(curr_obj, filename, indent, sort_keys, atomic)


def print_json(res):
    res_str = json.dumps(res, indent=2)

    # Colorize only for an interactive terminal. When stdout is piped/redirected/captured (e.g. an
    # LLM agent or `| jq`), emit plain JSON so ANSI escapes never corrupt the parsed output.
    if sys.stdout.isatty():
        res_str = highlight(res_str.encode('UTF-8'), lexers.JsonLexer(), formatters.TerminalFormatter()).strip()

    click.echo(res_str)
