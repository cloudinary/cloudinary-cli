#!/usr/bin/env python3
import click
from .utils import *
import cloudinary
from cloudinary import api
from cloudinary.utils import cloudinary_url as cld_url
from cloudinary import uploader as _uploader
from os import getcwd, walk
from os.path import abspath, dirname, join as path_join
from requests import get

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""Temporary configuration to use. To use permanent config:
echo \"export CLOUDINARY_URL=YOUR_CLOUDINARY_URL\" >> ~/.bash_profile && source ~/.bash_profile
""")
def cli(config):
    if config:
        cloudinary._config._parse_cloudinary_url(config)
    pass

@click.command("search", 
short_help="Search API Bindings",
help="""\b
Search API bindings
format: cld search <Lucene query syntax string> <options>
(eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10)
""")
@click.argument("query", nargs=-1)
@click.option("-f", "--with_field", multiple=True, help="Field to include in result")
@click.option("-s", "--sort_by", nargs=2, help="Sort search results by (field, <asc|desc>)")
@click.option("-a", "--aggregate", nargs=1, help="Aggregation to apply to the query")
@click.option("-n", "--max_results", nargs=1, default=10, help="Maximum results to return. default: 10 max: 500")
@click.option("-c", "--next_cursor", nargs=1, help="Continue a search using an existing cursor")
@click.option("-A", "--auto_paginate", is_flag=True, help="Return all results. Will call Admin API multiple times.")
@click.option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate")
@click.option("-ff", "--filter_fields", multiple=True, help="Filter fields to return")
@click.option("-d", "--doc", is_flag=True, help="Opens Search API documentation page")
def search(query, with_field, sort_by, aggregate, max_results, next_cursor, auto_paginate, force, filter_fields, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/search_api")
        exit(0)
    base_exp = cloudinary.Search().expression(" ".join(query))
    if auto_paginate:
        max_results = 500
    if with_field:
        for i in with_field:
            base_exp = base_exp.with_field(i)
    if sort_by:
        base_exp = base_exp.sort_by(*sort_by)
    if aggregate:
        base_exp = base_exp.aggregate(aggregate)
    base_exp = base_exp.max_results(max_results)
    exp = base_exp
    if next_cursor:
        exp = exp.next_cursor(next_cursor)
    res = exp.execute()

    all_results = res
    if auto_paginate and 'next_cursor' in res.keys():
        if not force:
            r = input(f"{res['total_count']} total results. {res.__dict__['rate_limit_remaining'] + 1} Admin API rate limit remaining.\nRunning this program will use {res['total_count']//500 + 1} Admin API calls. Continue? (Y/N) ")
            if r.lower() != 'y':
                print("Exiting. Please run again without -A.")
                exit(0)
            else:
                print("Continuing. You may use the -F flag to force auto_pagination.")

        while True:
            if 'next_cursor' not in res.keys():
                break
            
            exp = base_exp.next_cursor(res['next_cursor'])
            res = exp.execute()
            all_results['resources'] += res['resources']
        
        del all_results['time']

    if filter_fields:
        all_results['resources'] = list(map(lambda x: {k: x[k] if k in x.keys() else None for k in filter_fields + with_field}, all_results['resources']))
    log(all_results)


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
@click.argument("params", nargs=-1)
@click.option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@click.option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@click.option("-A", "--auto_paginate", is_flag=True, help="Return all results. Will call Admin API multiple times.")
@click.option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate")
@click.option("-ff", "--filter_fields", multiple=True, help="Filter fields to return")
@click.option("-ls", "--ls", is_flag=True, help="List all available functions in the Admin API")
@click.option("-d", "--doc", is_flag=True, help="Opens Admin API documentation page")
def admin(params, optional_parameter, optional_parameter_parsed, auto_paginate, force, filter_fields, ls, doc):
    if ls:
        print(get_help(api))
        exit(0)
    if doc:
        open_url("https://cloudinary.com/documentation/admin_api")
        exit(0)
    try:
        func = api.__dict__[params[0]]
        if not callable(func):
            raise Exception(F_FAIL(f"{func} is not callable."))
            exit(1)
    except:
        print(F_FAIL(f"Function {params[0]} does not exist in the Admin API."))
        exit(1)
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    if auto_paginate:
        options['max_results'] = 500
    res = func(*parameters, **{
        **options,
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
    })
    all_results = res['resources']
    if auto_paginate and 'next_cursor' in res.keys():
        if not force:
            r = input(f"{res.__dict__['rate_limit_remaining'] + 1} Admin API rate limit remaining. Continue? (Y/N) ")
            if r.lower() != 'y':
                print("Exiting. Please run again without -A.")
                exit(0)
            else:
                print("Continuing. You may use the -F flag to force auto_pagination.")

        while True:
            if 'next_cursor' not in res.keys():
                break
            res = func(*parameters, **{
                **options,
                **{k:v for k,v in optional_parameter},
                **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
                "next_cursor": res['next_cursor']
            })
            all_results += res['resources']
        
    if filter_fields:
        all_results = list(map(lambda x: {k: x[k] if k in x.keys() else None for k in filter_fields}, all_results))
    log(all_results)

@click.command("uploader", 
short_help="Upload API bindings",
help="""
\b
Upload API bindings
format: cld uploader <function> <parameters> <optional_parameters>
\teg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
\b
\teg. cld uploader rename flowers secret_flowers to_type=private
\t      OR
\t    cld uploader rename flowers secret_flowers -o to_type private
""")
@click.argument("params", nargs=-1)
@click.option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@click.option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@click.option("-ls", "--ls", is_flag=True, help="List all available functions in the Upload API")
@click.option("-d", "--doc", is_flag=True, help="Opens Upload API documentation page")
def uploader(params, optional_parameter, optional_parameter_parsed, ls, doc):
    if ls:
        print(get_help(_uploader))
        exit(0)
    if doc:
        open_url("https://cloudinary.com/documentation/image_upload_api_reference")
        exit(0)
    try:
        func = _uploader.__dict__[params[0]]
        if not callable(func):
            raise Exception(F_FAIL(f"{func} is not callable."))
            exit(1)
    except:
        print(F_FAIL(f"Function {params[0]} does not exist in the Upload API."))
        exit(1)
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **{
        **options,
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
    })
    log(res)

@click.command("upload_dir", 
help="""Upload a directory of assets and persist the directory structure""")
@click.argument("directory", default=".")
@click.option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@click.option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@click.option("-t", "--transformation", help="Transformation to apply on all uploads")
@click.option("-f", "--folder", default="", help="Specify the folder you would like to upload resources to in Cloudinary")
@click.option("-p", "--preset", help="Upload preset to use")
@click.option("-v", "--verbose", is_flag=True, help="Logs information after each upload")
@click.option("-vv", "--very_verbose", is_flag=True, help="Logs full details of each upload")
def upload_dir(directory, optional_parameter, optional_parameter_parsed, transformation, folder, preset, verbose, very_verbose):
    items, skipped = [], []
    dir_to_upload = abspath(path_join(getcwd(), directory))
    print(f"Uploading directory {dir_to_upload}")
    parent = dirname(dir_to_upload)
    current_dir_abs_path = dir_to_upload[len(parent)+1:]
    options = {
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
        "resource_type": "auto",
        "use_filename": True,
        "unqiue_filename": False,
        "raw_transformation": transformation,
        "upload_preset": preset
    }
    for root, _, files in walk(dir_to_upload):
        for fi in files:
            file_path = abspath(path_join(dir_to_upload, root, fi))
            mod_folder = path_join(folder, dirname(file_path[len(parent) + 1:]))
            try:
                _r = _uploader.upload(file_path, **options, folder=mod_folder)
                if verbose or very_verbose:
                    print(F_OK(f"Successfully uploaded {file_path} as {_r['public_id']}"))
                if very_verbose:
                    log(_r)
                items.append(_r['public_id'])
            except Exception as e:
                if verbose or very_verbose:
                    print(F_FAIL(f"Failed uploading {file_path}"))
                print(e)
                skipped.append(file_path)
                pass

    print(F_OK(f"\n{len(items)} resources uploaded:"))
    print(F_OK('\n'.join(items)))
    if len(skipped):
        print(F_FAIL(f"\n{len(skipped)} items skipped:"))
        print(F_FAIL('\n'.join(skipped)))

@click.command("url", help="Generate a cloudinary url")
@click.argument("public_id", required=True)
@click.argument("transformation", default="")
@click.option("-rt", "--resource_type", default="image", type=click.Choice(['image', 'video', 'raw']), help="Resource Type")
@click.option("-t", "--type", default="upload", type=click.Choice(['upload', 'private', 'authenticated', 'fetch', 'list']), help="Type of the resource")
@click.option("-o", "--open", is_flag=True, help="Open URL in your browser")
@click.option("-s", "--sign", is_flag=True, help="Generates a signed URL", default=False)
def url(public_id, transformation, resource_type, type, open, sign):
    if type == "authenticated":
        sign = True
    elif type == "list":
        public_id += ".json"
    res = cld_url(public_id, resource_type=resource_type, raw_transformation=transformation, type=type, sign_url=sign)[0]
    print(res)
    if open:
        open_url(res)

@click.command("config", help="Display current configuration")
def config():
    print('\n'.join(["{}:\t{}".format(k, v if k != "api_secret" else f"***************{v[-4:]}") for k, v in cloudinary._config.__dict__.items()]))


@click.command("make", help="Scaffold Cloudinary templates")
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
@click.option("-o", "--open", is_flag=True, help="Open URL in your browser")
def sample(transformation, open):
    cloudinary._config.cloud_name="demo"
    res = cld_url('sample', raw_transformation=transformation)[0]
    print(res)
    if open:
        open_url(res)

@click.command("couple", help="Open sample couple image")
@click.argument("transformation", default="")
@click.option("-o", "--open", is_flag=True, help="Open URL in your browser")
def couple(transformation, open):
    cloudinary._config.cloud_name="demo"
    res = cld_url('couple', raw_transformation=transformation)[0]
    print(res)
    if open:
        open_url(res)

@click.command("dog", help="Open sample dog video")
@click.argument("transformation", default="")
@click.option("-o", "--open", is_flag=True, help="Open URL in your browser")
def dog(transformation, open):
    cloudinary._config.cloud_name="demo"
    res = cld_url('dog', raw_transformation=transformation, resource_type="video")[0]
    print(res)
    if open:
        open_url(res)


@click.command("migrate", 
short_help="Migrate files using an existing auto-upload mapping and a file of URLs",
help="Migrate files using an existing auto-upload mapping and a file of URLs")
@click.argument("upload_mapping")
@click.argument("file")
@click.option("-d", "--delimiter", default="\n", help="Separator for the URLs. Default: New line")
@click.option("-v", "--verbose", is_flag=True)
def migrate(upload_mapping, file, delimiter, verbose):
    with open(file) as f:
        items = f.read().split(delimiter)
    mapping = api.upload_mapping(upload_mapping)
    _len = len(mapping['template'])
    items = map(lambda x: cld_url(mapping['folder'] + '/' + x[_len:]), filter(lambda x: x != '', items))
    for i in items:
        res = get(i[0])
        if res.status_code != 200:
            print(F_FAIL("Failed uploading asset: " + res.__dict__['headers']['X-Cld-Error']))
        elif verbose:
            print(F_OK(f"Uploaded {i[0]}"))
        

# Basic commands

cli.add_command(config)
cli.add_command(search)
cli.add_command(admin)
cli.add_command(uploader)
cli.add_command(url)

# Custom commands

cli.add_command(upload_dir)
cli.add_command(make)
cli.add_command(migrate)


# Sample resources

cli.add_command(sample)
cli.add_command(couple)
cli.add_command(dog)

def main():
    cli()