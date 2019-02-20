#!/usr/bin/env python3

import click
from .utils import *
import cloudinary
from cloudinary import api, utils
from cloudinary import uploader as _uploader
from os import getcwd
import os
from json import dumps
from pathlib import Path

terminal_dims = click.get_terminal_size()

CONTEXT_SETTINGS = dict(max_content_width=terminal_dims[0])
@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""
\b
Temporary cloudinary URL to use.
Please export your cloudinary URL to your terminal configuration file (eg. ~/.bash_profile) by doing the following:
echo "export CLOUDINARY_URL=YOUR_CLOUDINARY_URL" >> ~/.bash_profile && source ~/.bash_profile
""")
def cli(config):
    if config:
        cloudinary._config._parse_cloudinary_url(config)
    pass

@click.command("upload", help="Upload an asset using automatic resource type.")
@click.argument("file")
@click.option("-pid", "--public_id")
@click.option("-type", "--type", default="upload")
@click.option("-up", "--upload_preset")
@click.option("-t", "--transformation", help="A raw transformation (eg. f_auto,q_auto,w_500,e_vectorize)")
@click.option("-e", "--eager", help="An eager transformation or an array of eager transformations")
@click.option("-uo", "--upload_options", help="""
\b
Additional upload options to use 
Usage: -uo <upload_option> <option_value>
(eg. cld upload test.jpg -uo use_filename True -uo tags test,dogs,wow -uo context "alt:woof|caption:ruff day")
""", multiple=True, nargs=2)
@click.option("-view", "--view", is_flag=True)
def upload(file, public_id, type, upload_preset, transformation, eager, upload_options, view):
    print(upload_options)
    if eager:
        eager = parse_option_value(eager)
    options = {k: v if k != "eager" else parse_option_value(v) for k,v in upload_options} if upload_options else {}
    res = _uploader.upload(file, public_id=public_id, type=type, resource_type="auto", upload_preset=upload_preset, raw_transformation=transformation, eager=eager, **options)
    log(res)
    
    if view:
        open_url(res['url'])

@click.command("search", help="""
\b
Search API bindings
Usage: cld search <Lucene query syntax search string> <options>
(eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10)
""")
@click.argument("query", nargs=-1)
@click.option("-f", "--with_field", multiple=True)
@click.option("-s", "--sort_by", nargs=2)
@click.option("-a", "--aggregate", nargs=1)
@click.option("-n", "--max_results", nargs=1, default=10)
@click.option("-c", "--next_cursor", nargs=1)
def search(query, with_field, sort_by, aggregate, max_results, next_cursor):
    exp = cloudinary.Search().expression(" ".join(query))
    if with_field:
        for i in with_field:
            exp = exp.with_field(i)
    if sort_by:
        exp = exp.sort_by(*sort_by)
    if aggregate:
        exp = exp.aggregate(aggregate)
    if next_cursor:
        exp = exp.next_cursor(next_cursor)
    res = exp.max_results(max_results).execute()
    log(res)

@click.command("admin", help="""
\b
Admin API bindings
format: cld admin <function> <parameters> <keyword_arguments>
\teg. cld admin resources max_results=10 tags=sample
""")
@click.argument("params", nargs=-1)
@click.option("-ls", "--ls", is_flag=True, help="List all available functions")
def admin(params, ls):
    if ls:
        print(get_help(api))
        exit(0)
    try:
        func = api.__dict__[params[0]]
        if not callable(func):
            raise Exception(f"{func} is not callable.")
            exit(1)
    except:
        print(f"Function {params[0]} does not exist in the Admin API.")
        exit(1)
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **options) 
    log(dumps(res, indent=2))


@click.command("uploader", help="""
\b
Upload API bindings
format: cld uploader <function> <parameters> <keyword_arguments>
\teg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers
\t    cld uploader rename flowers secret_flowers to_type=private
""")
@click.argument("params", nargs=-1)
@click.option("-ls", "--ls", is_flag=True, help="List all available functions")
def uploader(params, ls):
    if ls:
        print(get_help(_uploader))
        exit(0)
    try:
        func = _uploader.__dict__[params[0]]
        if not callable(func):
            raise Exception(f"{func} is not callable.")
            exit(1)
    except:
        print(f"Function {params[0]} does not exist in the Upload API.")
        exit(1)
    # if (callable(func) and params[0][0].islower()):
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **options)
    log(dumps(res, indent=2))

@click.command("fetch", help="""
\b
Fetches an image
""")
@click.argument("url", nargs=1)
@click.option("-t", "--transformation")
def fetch(args, transformation):
    res = utils.cloudinary_url(url, type="fetch", raw_transformation=transformation)[0]
    open_url(res)

@click.command("upload_dir", help=
"""
\b
Upload a directory of assets and persist the directory structure
\tUsage: cld upload_dir <path_to_directory>
""")
@click.argument("directory", default=".")
@click.option("-t", "--transformation", help="Transformation to apply on all uploads")
@click.option("-f", "--folder", default="", help="Specify the folder you would like to upload resources to in Cloudinary")
@click.option("-p", "--preset", help="Upload preset to use")
@click.option("-v", "--verbose", is_flag=True)
@click.option("-vv", "--very_verbose", is_flag=True)
@click.option("-nr", "--non_recursive", is_flag=True) # Not implemented yet :)
def upload_dir(directory, transformation, folder, preset, verbose, very_verbose, non_recursive):
    items, skipped = [], []
    dir_to_upload = os.path.abspath(os.path.join(os.getcwd(), directory))
    print(f"Uploading directory {dir_to_upload}")
    parent = os.path.dirname(dir_to_upload)
    current_dir_abs_path = dir_to_upload[len(parent)+1:]
    for root, _, files in os.walk(dir_to_upload):
        for fi in files:
            file_path = os.path.abspath(os.path.join(dir_to_upload, root, fi))
            full_path = file_path[len(parent) + 1:] if folder == "" else folder + "/" + file_path[len(parent) + 1:]
            if verbose or very_verbose:
                print(f"Uploading {file_path} as {full_path}... ", end="")
            pid = file_path[len(parent) + 1:]
            suffix = len(Path(pid).suffix)
            if suffix:
                pid = pid[:-suffix]
            try:
                _r = _uploader.upload(file_path, public_id=f"{pid}", folder=folder, resource_type="auto", upload_preset=preset, raw_transformation=transformation)
                if verbose or very_verbose:
                    print("Success!")
                if very_verbose:
                    log(_r)
                items.append(_r['public_id'])
            except Exception as e:
                
                if verbose or very_verbose:
                    print("Failed!")
                print(e)
                skipped.append(file_path)

    print(f"\n{len(items)} resources uploaded:")
    print('\n'.join(items))
    if len(skipped):
        print(f"\n{len(skipped)} items skipped:")
        print('\n'.join(skipped))

@click.command("url", help=
"""
\b
Generate a cloudinary url
""")
@click.argument("pid")
@click.argument("transformation", default="")
@click.option("-t", "--resource_type", default="image")
@click.option("-o", "--open", is_flag=True)
def url(pid, resource_type, transformation, open):
    res = utils.cloudinary_url(pid, resource_type=resource_type, raw_transformation=transformation)[0]
    print(res)
    if open:
        open_url(res)

@click.command("ls", help="""
\b
List all resources by calling the Admin API multiple times
\tformat: cld ls <fields to return or resource search filters>
\teg. cld ls
\teg. Find all private resources and return the public_id
\t    cld ls type=private public_id
""")
@click.argument("fields_and_options", nargs=-1)
def ls(fields_and_options):
    fields, options = [], {}
    for x in fields_and_options:
        if "=" in x:
            tmp = x.split("=")
            options[tmp[0]] = tmp[1]
        else:
            fields.append(x)
    count = 0
    resources = []
    cursor = None
    while True:
        res = api.resources(max_results=500, next_cursor=cursor, **options)
        resources += res['resources']
        count += 1
        if 'cursor' in res.keys():
            cursor = res['cursor']
        else:
            break
    resources = list(map(lambda x: {key: x[key] for key in fields}, resources)) if len(fields) > 1 else list(map(lambda x: x[fields[0]], resources)) if len(fields) > 0 else resources
    log("[" + ",\n".join([dumps(x, indent=2) for x in resources]) + "]")
    print(f"API called {count} time(s).")
    print(f"{len(resources)} resources found.")


@click.command("make", help="Scaffold cloudinary code templates") # scaffolding
@click.argument("template", nargs=-1)
def make(template):
    language = "html"
    if template[-1] in TEMPLATE_EXTS.keys():
        language = template[-1]
        template = template[:-1]
    elif template[0] in TEMPLATE_EXTS.keys():
        language = template[0]
        template = template[1:]
    print(load_template(language, '_'.join(template)))


@click.command("sample", help="Sample flowers image")
@click.argument("transformation", default="")
def sample(transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url('sample', raw_transformation=transformation)[0]
    open_url(res)

@click.command("couple", help="Sample couple image")
@click.argument("transformation", default="")
def couple(transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url('couple', raw_transformation=transformation)[0]
    open_url(res)

@click.command("dog", help="Sample dog video")
@click.argument("transformation", default="")
def dog(transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url('dog', raw_transformation=transformation, resource_type="video")[0]
    open_url(res)

@click.command("whoami", help="Current configuration")
def whoami():
    print(f"Cloud Name: \t{cloudinary._config.cloud_name}\nAPI Key: \t{cloudinary._config.api_key}")


cli.add_command(upload)
cli.add_command(search)
cli.add_command(make)
cli.add_command(admin)
cli.add_command(uploader)
cli.add_command(fetch)
cli.add_command(upload_dir)
cli.add_command(url)
cli.add_command(ls)
cli.add_command(whoami)


cli.add_command(sample)
cli.add_command(couple)
cli.add_command(dog)


def main():
    # ctx = click.Context(cli, max_content_width=terminal_dims[0], terminal_width=terminal_dims[0])
    # print(ctx.__dict__)
    cli()