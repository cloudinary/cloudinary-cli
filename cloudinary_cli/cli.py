#!/usr/bin/env python3
import click
from .utils import *
import cloudinary
from cloudinary import api
from cloudinary.utils import cloudinary_url as cld_url
from cloudinary import uploader as _uploader
from os import getcwd, walk, sep, remove, rmdir, listdir
from os.path import abspath, dirname, join as path_join, isfile, splitext, split
from requests import get
from json import loads, dumps
from hashlib import md5
from itertools import product
from functools import reduce
from webbrowser import open as open_url
from threading import Thread, active_count
from time import sleep
import csv as _csv

CONTEXT_SETTINGS = dict(max_content_width=click.get_terminal_size()[0], terminal_width=click.get_terminal_size()[0])

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="""Temporary configuration to use. To use permanent config:
echo \"export CLOUDINARY_URL=YOUR_CLOUDINARY_URL\" >> ~/.bash_profile && source ~/.bash_profile
""")
@click.option("-C", "--config_saved", help="""Saved configuration to use - see `config` command""")
def cli(config, config_saved):
    if config:
        cloudinary._config._parse_cloudinary_url(config)
    elif config_saved:
        cloudinary._config._parse_cloudinary_url(loads(open(CLOUDINARY_CLI_CONFIG_FILE).read())[config_saved])
    pass

@click.command("search", 
short_help="Search API Bindings",
help="""\b
Search API bindings
format: cld search <Lucene query syntax string> <options>
eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10
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
@click.option("--json", nargs=1, help="Save output as a JSON. Usage: --json <filename>")
@click.option("--csv", nargs=1, help="Save output as a CSV. Usage: --csv <filename>")
@click.option("-d", "--doc", is_flag=True, help="Opens Search API documentation page")
def search(query, with_field, sort_by, aggregate, max_results, next_cursor, auto_paginate, force, filter_fields, json, csv, doc):
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
            r = input("{} total results. {} Admin API rate limit remaining.\nRunning this program will use {} Admin API calls. Continue? (Y/N) ".format(res['total_count'], res.__dict__['rate_limit_remaining'] + 1, res['total_count']//500 + 1))
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
    ff = []
    if filter_fields:
        ff = []
        for f in list(filter_fields):
            if "," in f:
                ff += f.split(",")
            else:
                ff.append(f)
        ff = tuple(ff) + with_field
        all_results['resources'] = list(map(lambda x: {k: x[k] if k in x.keys() else None for k in ff}, all_results['resources']))
    log(all_results)

    if json:
        write_out(all_results['resources'], json)
    
    if csv:
        all_results = all_results['resources']
        f = open('{}.csv'.format(csv), 'w')
        if ff == []:
            ff = list(all_results[0].keys())
        writer = _csv.DictWriter(f, fieldnames=list(ff))

        writer.writeheader()
        writer.writerows(all_results)

        f.close()

        print('Saved search to \'{}.csv\''.format(csv))
        #write to csv



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
@click.option("-ls", "--ls", is_flag=True, help="List all available functions in the Admin API")
@click.option("--save", nargs=1, help="Save output to a file")
@click.option("-d", "--doc", is_flag=True, help="Opens Admin API documentation page")
def admin(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/admin_api")
        exit(0)
    if ls or len(params) < 1:
        print(get_help(api))
        exit(0)
    try:
        func = api.__dict__[params[0]]
        if not callable(func):
            raise Exception(F_FAIL("{} is not callable.".format(func)))
            exit(1)
    except:
        print(F_FAIL("Function {} does not exist in the Admin API.".format(params[0])))
        exit(1)
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **{
        **options,
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
    })
    log(res)
    if save:
        write_out(all_results, save)

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
@click.option("--save", nargs=1, help="Save output to a file")
@click.option("-d", "--doc", is_flag=True, help="Opens Upload API documentation page")
def uploader(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/image_upload_api_reference")
        exit(0)
    if ls or len(params) < 1:
        print(get_help(_uploader))
        exit(0)
    try:
        func = _uploader.__dict__[params[0]]
        if not callable(func):
            raise Exception(F_FAIL("{} is not callable.".format(func)))
            exit(1)
    except:
        print(F_FAIL("Function {} does not exist in the Upload API.".format(params[0])))
        exit(1)
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **{
        **options,
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
    })
    log(res)
    if save:
        write_out(all_results, save)

@click.command("upload_dir", 
help="""Upload a directory of assets and persist the directory structure""")
@click.argument("directory", default=".")
@click.option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@click.option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@click.option("-t", "--transformation", help="Transformation to apply on all uploads")
@click.option("-f", "--folder", default="", help="Specify the folder you would like to upload resources to in Cloudinary")
@click.option("-p", "--preset", help="Upload preset to use")
@click.option("-v", "--verbose", is_flag=True, help="Logs information after each upload")
def upload_dir(directory, optional_parameter, optional_parameter_parsed, transformation, folder, preset, verbose):
    items, skipped = [], []
    dir_to_upload = abspath(path_join(getcwd(), directory))
    print("Uploading directory '{}'".format(dir_to_upload))
    parent = dirname(dir_to_upload)
    current_dir_abs_path = dir_to_upload[len(parent)+1:]
    options = {
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
        "resource_type": "auto",
        "invalidate": True,
        "unique_filename": False,
        "use_filename": True,
        "raw_transformation": transformation,
        "upload_preset": preset
    }

    threads = []

    def upload_multithreaded(file_path, items, skipped, v, **kwargs):
        try:
            _r = _uploader.upload(file_path, **kwargs)
            print(F_OK("Successfully uploaded {} as {}".format(file_path, _r['public_id'])))
            if v:
                log(_r)
            items.append(_r['public_id'])
        except Exception as e:
            print(F_FAIL("Failed uploading {}".format(file_path)))
            print(e)
            skipped.append(file_path)
            pass

    for root, _, files in walk(dir_to_upload):
        for fi in files:
            file_path = abspath(path_join(dir_to_upload, root, fi))
            mod_folder = path_join(folder, dirname(file_path[len(parent) + 1:]))
            if split(file_path)[1][0] == ".":
                continue
            options = {**options, "folder": mod_folder}
            threads.append(Thread(target=upload_multithreaded, args=(file_path, items, skipped, verbose), kwargs=options))

    for t in threads:
        while active_count() >= 30:
            # prevent concurrency overload
            sleep(1)
        t.start()
        sleep(1/10)

    for t in threads: t.join()

    print(F_OK("\n{} resources uploaded:".format(len(items))))
    print(F_OK('\n'.join(items)))
    if len(skipped):
        print(F_FAIL("\n{} items skipped:".format(len(skipped))))
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

@click.command("config", help="Display current configuration, and manage additional configurations")
@click.option("-n", "--new", help="""\b Set an additional configuration
eg. cld config -n <NAME> <CLOUDINARY_URL>""", nargs=2)
@click.option("-ls", "--ls", help="List all configurations", is_flag=True)
@click.option("-rm", "--rm", help="Delete an additional configuration", nargs=1)
def config(new, ls, rm):
    if not (new or ls or rm):
        print('\n'.join(["{}:\t{}".format(k, v if k != "api_secret" else "***************{}".format(v[-4:])) for k, v in cloudinary._config.__dict__.items()]))
        exit(0)

    with open(CLOUDINARY_CLI_CONFIG_FILE, "r+") as f:
        fi = f.read()
        cfg = loads(fi) if fi != "" else {}
        f.close()
    if new:
        try:
            cloudinary._config._parse_cloudinary_url(new[1])
            cfg[new[0]] = new[1]
            api.ping()
            with open(CLOUDINARY_CLI_CONFIG_FILE, "w") as f:
                f.write(dumps(cfg))
                f.close()
            print("Config '{}' saved!".format(new[0]))
        except:
            print("Invalid Cloudinary URL: {}".format(new[1]))
            exit(1)
        exit(0)
    if ls:
        print("\n".join(cfg.keys()))
        exit(0)
    if rm:
        if rm not in cfg.keys():
            print("Configuration '{}' not found.".format(rm))
            exit(1)
        del cfg[rm]
        open(CLOUDINARY_CLI_CONFIG_FILE, "w").write(dumps(cfg))
        print("Configuration '{}' deleted".format(rm))

@click.command("make", short_help="Scaffold Cloudinary templates.",
help="""\b
Scaffold Cloudinary templates.
eg. cld make product gallery
""")
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

        
@click.command("sync",
short_help="Synchronize between a local directory between a Cloudinary folder",
help="Synchronize between a local directory between a Cloudinary folder while preserving directory structure")
@click.argument("local_folder")
@click.argument("cloudinary_folder")
@click.option("--push", help="Push will sync the local directory to the cloudinary directory", is_flag=True)
@click.option("--pull", help="Pull will sync the cloudinary directory to the local directory", is_flag=True)
@click.option("-v", "--verbose", is_flag=True, help="Logs information after each upload")
def sync(local_folder, cloudinary_folder, push, pull, verbose):
    if push == pull:
        print("Please use either the '--push' OR '--pull' options")
        exit(1)
   
    etag = lambda f: md5(open(f, 'rb').read()).hexdigest()

    def walk_dir(folder):
        all_files = {}
        for root, _, files in walk(folder):
            for _file in files:
                all_files[splitext(path_join(root, _file)[len(folder)+1:])[0]] = {"etag": etag(path_join(root, _file)), "path": path_join(root, _file)}
        return all_files

    def query_cld_folder(folder):
        next_cursor = None
        items = {}
        while True:
            res = cloudinary.Search().expression("{}/*".format(folder)).next_cursor(next_cursor).with_field("image_analysis").max_results(500).execute()
            for item in res['resources']:
                items[item['public_id'][len(folder)+1:]] = {"etag": item['image_analysis']['etag'], "resource_type": item['resource_type'], "public_id": item['public_id'], "type": item['type'], "format": item['format']}
            if 'next_cursor' not in res.keys():
                break
            else:
                next_cursor = res['next_cursor']
        return items

    files = walk_dir(abspath(local_folder))    
    print("Found {} items in local folder '{}'".format(len(files.keys()), local_folder))
    cld_files = query_cld_folder(cloudinary_folder)
    print("Found {} items in Cloudinary folder '{}'".format(len(cld_files.keys()), cloudinary_folder))
    files_ = set(files.keys())
    cld_files_ = set(cld_files.keys())

    files_in_cloudinary_nin_local = cld_files_ - files_
    files_in_local_nin_cloudinary = files_ - cld_files_
    skipping = 0

    if push:
            
        files_to_delete_from_cloudinary = list(cld_files_ - files_)
        files_to_push = files_ - cld_files_
        files_to_check = files_ - files_to_push
        print("\nCalculating differences...\n")
        for f in files_to_check:
            if files[f]['etag'] == cld_files[f]['etag']:
                if verbose:
                    print(F_WARN("{} already exists in Cloudinary".format(f)))
                skipping += 1
            else:
                files_to_push.add(f)
        print("Skipping upload for {} items".format(skipping))
        if len(files_to_delete_from_cloudinary) > 0:
            print("Deleting {} resources from Cloudinary folder '{}'".format(len(files_to_delete_from_cloudinary), cloudinary_folder))
            files_to_delete_from_cloudinary = list(map(lambda x: cld_files[x], files_to_delete_from_cloudinary))
            
            for i in product({"upload", "private", "authenticated"}, {"image", "video", "raw"}):
                batch = list(map(lambda x: x['public_id'], filter(lambda x: x["type"] == i[0] and x["resource_type"] == i[1], files_to_delete_from_cloudinary)))
                if len(batch) > 0:
                    print("Deleting {} resources with type '{}' and resource_type '{}'".format(len(batch), *i))
                    counter = 0
                    while counter*100 < len(batch) and len(batch) > 0:
                        counter += 1
                        res = api.delete_resources(batch[(counter-1)*100:counter*100], invalidate=True, resource_type=i[1], type=i[0])
                        num_deleted = reduce(lambda x, y: x + 1 if y == "deleted" else x, res['deleted'].values(), 0)
                        if verbose:
                            log(res)
                        if num_deleted != len(batch):
                            print(F_FAIL("Failed deletes:\n{}".format("\n".join(list(map(lambda x: x[0], filter(lambda x: x[1] != 'deleted', res['deleted'].items())))))))
                        else:
                            print(F_OK("Deleted {} resources".format(num_deleted)))

        to_upload = list(filter(lambda x: split(x)[1][0] != ".", files_to_push))
        print("Uploading {} items to Cloudinary folder '{}'".format(len(to_upload), cloudinary_folder))

        threads = []

        def threaded_upload(options, path, verbose):
            res = _uploader.upload(path, **options)
            if verbose:
                print(F_OK("Uploaded '{}'".format(res['public_id'])))

        for i in to_upload:
            modif_folder = path_join(cloudinary_folder, sep.join(i.split(sep)[:-1]))
            options = {'use_filename': True, 'unique_filename': False, 'folder': modif_folder, 'invalidate': True, 'resource_type': 'auto'}
            threads.append(Thread(target=threaded_upload, args=(options, files[i]['path'], verbose)))
        
        for t in threads:
            while active_count() >= 30:
                # prevent concurrency overload
                sleep(1)
            t.start()
            sleep(1/10)

        [t.join() for t in threads]

        print("Done!")
        
    else:
        files_to_delete_local = list(files_in_local_nin_cloudinary)
        files_to_pull = files_in_cloudinary_nin_local
        files_to_check = cld_files_ - files_to_pull
        
        print("\nCalculating differences...\n")
        for f in files_to_check:
            if files[f]['etag'] == cld_files[f]['etag']:
                if verbose:
                    print(F_WARN("{} already exists locally".format(f)))
                skipping += 1
            else:
                files_to_pull.add(f)
        print("Skipping download for {} items".format(skipping))

        def delete_empty_folders(root, verbose, remove_root=False):
            if not isdir(root):
                return

            files = listdir(root)
            if len(files):
                for f in files:
                    fullpath = path_join(root, f)
                    if isdir(fullpath):
                        delete_empty_folders(fullpath, verbose, True)
            
            files = listdir(root)
            if len(files) == 0 and remove_root:
                if verbose:
                    print("Removing empty folder '{}'".format(root))
                rmdir(root)

        def create_required_directories(root, verbose):
            if isdir(root):
                return
            else:
                create_required_directories(sep.join(root.split(sep)[:-1]), verbose)
                if verbose:
                    print("Creating directory '{}'".format(root))
                mkdir(root)     

        print("Deleting {} local files...".format(len(files_to_delete_local)))
        for i in files_to_delete_local:
            remove(abspath(files[i]['path']))
            if verbose:
                print("Deleted '{}'".format(abspath(files[i]['path'])))

        print("Deleting empty folders...")
        
        delete_empty_folders(local_folder, verbose)

        print("Downloading {} files from Cloudinary".format(len(files_to_pull)))
        
        threads = []
        
        def threaded_pull(local_path, verbose, cld_files):
            with open(local_path, "wb") as f:
                to_download = cld_files[i]
                r = get(cld_url(to_download['public_id'], resource_type=to_download['resource_type'], type=to_download['type'])[0])
                f.write(r.content)
                f.close()
            if verbose:
                print(F_OK("Downloaded '{}' to '{}'".format(i, local_path)))

        for i in files_to_pull:
            local_path = abspath(path_join(local_folder, i + "." + cld_files[i]['format'] if cld_files[i]['resource_type'] != 'raw' else i))
            create_required_directories(split(local_path)[0], verbose)

            threads.append(Thread(target=threaded_pull, args=(local_path, verbose, cld_files)))

        for t in threads:
            while active_count() >= 30:
                # prevent concurrency overload
                sleep(1)
            t.start()
            sleep(1/10)

        [t.join() for t in threads]
        
        print("Done!")

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
    items = map(lambda x: cld_url(path_join(mapping['folder'], x[len(mapping['template']):])), filter(lambda x: x != '', items))
    for i in items:
        res = get(i[0])
        if res.status_code != 200:
            print(F_FAIL("Failed uploading asset: " + res.__dict__['headers']['X-Cld-Error']))
        elif verbose:
            print(F_OK("Uploaded {}".format(i[0])))

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
cli.add_command(sync)

# Sample resources

cli.add_command(sample)
cli.add_command(couple)
cli.add_command(dog)

def main():
    cli()