#!/usr/bin/env python3

import click
from .utils import *
import cloudinary
from cloudinary import api, utils
from cloudinary import uploader as _uploader
from os import getcwd, walk
from os.path import abspath, dirname, basename, join as path_join

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""Temporary cloudinary URL to use. To use permanent configuration, export your cloudinary URL to your terminal configuration file (eg. ~/.bash_profile) by doing the following:
echo "export CLOUDINARY_URL=YOUR_CLOUDINARY_URL" >> ~/.bash_profile && source ~/.bash_profile
""")
def cli(config):
    if config:
        cloudinary._config._parse_cloudinary_url(config)
    pass

@click.command("upload", help="Upload an asset using the `auto` resource type")
@click.argument("file", required=True)
@click.option("-pid", "--public_id")
@click.option("-type", "--type", default="upload", type=click.Choice(['upload', 'private', 'authenticated']))
@click.option("-up", "--upload_preset")
@click.option("-t", "--transformation", help="A raw transformation (eg. f_auto,q_auto,w_500,e_vectorize)")
@click.option("-e", "--eager", help="An eager transformation or an array of eager transformations")
@click.option("-uo", "--upload_options", help="""Additional upload options to use 
\b
\tUsage: -uo <upload_option> <option_value>
\t(eg. cld upload test.jpg -uo use_filename True -uo tags test,dogs,wow -uo context "alt:woof|caption:ruff day")
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

@click.command("search", 
short_help="Search API Bindings",
help="""\b
Search API bindings
Usage: cld search <Lucene query search string> <options>
(eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10)
""")
@click.argument("query", nargs=-1)
@click.option("-f", "--with_field", multiple=True, help="Field to include in result")
@click.option("-s", "--sort_by", nargs=2, help="Sort search results by (field, <asc|desc>)")
@click.option("-a", "--aggregate", nargs=1, help="Aggregation to apply to the query")
@click.option("-n", "--max_results", nargs=1, default=10, help="Maximum results to return. default: 10 max: 500")
@click.option("-c", "--next_cursor", nargs=1, help="Continue a search using an existing cursor")
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

@click.command("admin",
short_help="Admin API bindings",
help="""\b
Admin API bindings
format: cld admin <function> <parameters> <optional_parameters>
\teg. cld admin resources max_results=10 tags=sample
\t      OR
\t    cld admin resources -o max_results 10 -o tags sample
\t      OR
\t    cld admin resources max_results=10 -o tags=sample
""")
@click.argument("params", nargs=-1, required=True)
@click.option("-o", "--optional_param", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@click.option("-ls", "--ls", is_flag=True, help="List all available functions in the Admin API")
def admin(params, optional_param, ls):
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
    for i in optional_param:
        options[i[0]] = i[1]
    res = func(*parameters, **options) 
    log(res)

@click.command("uploader", 
short_help="Upload API bindings",
help="""
\b
Upload API bindings
format: cld uploader <function> <parameters> <optional_parameters>
\teg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers

\b
\teg. cld uploader rename flowers secret_flowers to_type=private
\t      OR
\t    cld uploader rename flowers secret_flowers -o to_type private
""")
@click.argument("params", nargs=-1, required=True)
@click.option("-o", "--optional_param", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@click.option("-ls", "--ls", is_flag=True, help="List all available functions in the Upload API")
def uploader(params, optional_param, ls):
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
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    for i in optional_param:
        options[i[0]] = i[1]
    res = func(*parameters, **options)
    log(res)

@click.command("fetch", help="Fetches an image")
@click.argument("url", nargs=1, required=True)
@click.option("-t", "--transformation", help="Transformation string to apply to the fetch")
def fetch(url, transformation):
    res = utils.cloudinary_url(url, type="fetch", raw_transformation=transformation)[0]
    open_url(res)
    log(res)

@click.command("upload_dir", 
short_help="Upload a local directory of assets",
help="""\b
Upload a directory of assets and persist the directory structure
\tUsage: cld upload_dir <path_to_directory>
""")
@click.argument("directory", default=".")
@click.option("-t", "--transformation", help="Transformation to apply on all uploads")
@click.option("-f", "--folder", default="", help="Specify the folder you would like to upload resources to in Cloudinary")
@click.option("-p", "--preset", help="Upload preset to use")
@click.option("-v", "--verbose", is_flag=True)
@click.option("-vv", "--very_verbose", is_flag=True)
def upload_dir(directory, transformation, folder, preset, verbose, very_verbose):
    items, skipped = [], []
    dir_to_upload = abspath(path_join(getcwd(), directory))
    print(f"Uploading directory {dir_to_upload}")
    parent = dirname(dir_to_upload)
    current_dir_abs_path = dir_to_upload[len(parent)+1:]
    for root, _, files in walk(dir_to_upload):
        for fi in files:
            file_path = abspath(path_join(dir_to_upload, root, fi))
            full_path = file_path[len(parent) + 1:] if folder == "" else folder + "/" + file_path[len(parent) + 1:]
            if verbose or very_verbose:
                print(f"Uploading {file_path} as {full_path}... ", end="")
            pid = basename(file_path[len(parent) + 1:])
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

@click.command("url", help="Generate a cloudinary url")
@click.argument("public_id", required=True)
@click.argument("transformation", default="")
@click.option("-rt", "--resource_type", default="image")
@click.option("-t", "--type", default="upload")
@click.option("-o", "--open", is_flag=True)
def url(public_id, transformation, resource_type, type, open):
    res = utils.cloudinary_url(public_id, resource_type=resource_type, raw_transformation=transformation, type=type)[0]
    print(res)
    if open:
        open_url(res)

@click.command("whoami", help="Display current configuration")
def whoami():
    print(f"cloud_name: \t{cloudinary._config.cloud_name}\napi_key: \t{cloudinary._config.api_key}")

@click.command("ls",
short_help="Lists all resources based on resource search parameters in your cloud, and returns specific fields (all if none is specified)",
help="""\b
List all resources by calling the Admin API multiple times
\tformat: cld ls <FIELDS_TO_RETURN and/or RESOURCE_SEARCH_PARAMS>
\teg. cld ls
\teg. Find all private resources and return the public_id
\t    cld ls type=private public_id
""")
@click.argument("fields_and_search_parameters", nargs=-1)
def ls(fields_and_search_parameters):
    fields, options = [], {}
    for x in fields_and_search_parameters:
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
        if 'next_cursor' in res.keys():
            cursor = res['next_cursor']
        else:
            break
    resources = list(map(lambda x: {key: x[key] for key in fields}, resources)) if len(fields) > 1 else list(map(lambda x: x[fields[0]], resources)) if len(fields) > 0 else resources
    log(resources)
    print(f"API called {count} time(s)."),
    print(f"{len(resources)} resources found.")


@click.command("make", help="Scaffold cloudinary code templates")
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


@click.command("sample", help="Open sample flowers image")
@click.argument("transformation", default="")
def sample(transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url('sample', raw_transformation=transformation)[0]
    open_url(res)

@click.command("couple", help="Open sample couple image")
@click.argument("transformation", default="")
def couple(transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url('couple', raw_transformation=transformation)[0]
    open_url(res)

@click.command("dog", help="Open sample dog video")
@click.argument("transformation", default="")
def dog(transformation):
    cloudinary._config.cloud_name="demo"
    res = utils.cloudinary_url('dog', raw_transformation=transformation, resource_type="video")[0]
    open_url(res)

# Basic commands

cli.add_command(whoami)
cli.add_command(upload)
cli.add_command(search)
cli.add_command(admin)
cli.add_command(uploader)
cli.add_command(fetch)
cli.add_command(url)

# Custom commands

cli.add_command(upload_dir)
cli.add_command(url)
cli.add_command(ls)
cli.add_command(make)

# Sample resources

cli.add_command(sample)
cli.add_command(couple)
cli.add_command(dog)

def main():
    cli()