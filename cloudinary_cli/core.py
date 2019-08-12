# from .utils import *
# from webbrowser import open as open_url
# from csv import DictWriter
# from cloudinary.utils import cloudinary_url as cld_url
# from cloudinary import api, uploader as _uploader
# from click import command, argument, option, Choice

# @command("search",
#          short_help="Search API Bindings",
#          help="""\b
# Search API bindings
# format: cld search <Lucene query syntax string> <options>
# eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10
# """)
# @argument("query", nargs=-1)
# @option("-f", "--with_field", multiple=True, help="Field to include in result")
# @option("-s", "--sort_by", nargs=2, help="Sort search results by (field, <asc|desc>)")
# @option("-a", "--aggregate", nargs=1, help="Aggregation to apply to the query")
# @option("-n", "--max_results", nargs=1, default=10, help="Maximum results to return. default: 10 max: 500")
# @option("-c", "--next_cursor", nargs=1, help="Continue a search using an existing cursor")
# @option("-A", "--auto_paginate", is_flag=True, help="Return all results. Will call Admin API multiple times.")
# @option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate")
# @option("-ff", "--filter_fields", multiple=True, help="Filter fields to return")
# @option("--json", nargs=1, help="Save output as a JSON. Usage: --json <filename>")
# @option("--csv", nargs=1, help="Save output as a CSV. Usage: --csv <filename>")
# @option("-d", "--doc", is_flag=True, help="Opens Search API documentation page")
# def search(query, with_field, sort_by, aggregate, max_results, next_cursor, auto_paginate, force, filter_fields, json, csv, doc):
#     if doc:
#         open_url("https://cloudinary.com/documentation/search_api")
#         exit(0)
#     base_exp = cloudinary.Search().expression(" ".join(query))
#     if auto_paginate:
#         max_results = 500
#     if with_field:
#         for i in with_field:
#             base_exp = base_exp.with_field(i)
#     if sort_by:
#         base_exp = base_exp.sort_by(*sort_by)
#     if aggregate:
#         base_exp = base_exp.aggregate(aggregate)
#     base_exp = base_exp.max_results(max_results)
#     exp = base_exp
#     if next_cursor:
#         exp = exp.next_cursor(next_cursor)
#     res = exp.execute()

#     all_results = res
#     if auto_paginate and 'next_cursor' in res.keys():
#         if not force:
#             r = input("{} total results. {} Admin API rate limit remaining.\nRunning this program will use {} Admin API calls. Continue? (Y/N) ".format(res['total_count'], res.__dict__['rate_limit_remaining'] + 1, res['total_count']//500 + 1))
#             if r.lower() != 'y':
#                 print("Exiting. Please run again without -A.")
#                 exit(0)
#             else:
#                 print("Continuing. You may use the -F flag to force auto_pagination.")

#         while True:
#             if 'next_cursor' not in res.keys():
#                 break
            
#             exp = base_exp.next_cursor(res['next_cursor'])
#             res = exp.execute()
#             all_results['resources'] += res['resources']
        
#         del all_results['time']
#     ff = []
#     if filter_fields:
#         ff = []
#         for f in list(filter_fields):
#             if "," in f:
#                 ff += f.split(",")
#             else:
#                 ff.append(f)
#         ff = tuple(ff) + with_field
#         all_results['resources'] = list(map(lambda x: {k: x[k] if k in x.keys() else None for k in ff}, all_results['resources']))
#     log(all_results)

#     if json:
#         write_out(all_results['resources'], json)
    
#     if csv:
#         all_results = all_results['resources']
#         f = open('{}.csv'.format(csv), 'w')
#         if ff == []:
#             ff = list(all_results[0].keys())
#         writer = DictWriter(f, fieldnames=list(ff))

#         writer.writeheader()
#         writer.writerows(all_results)

#         f.close()

#         print('Saved search to \'{}.csv\''.format(csv))
#         #write to csv



# @command("admin",
#          short_help="Admin API bindings",
#          help="""\b
# Admin API bindings
# format: cld admin <function> <parameters> <optional_parameters>
# \teg. cld admin resources max_results=10 tags=sample
# \t      OR
# \t    cld admin resources -o max_results 10 -o tags sample
# \t      OR
# \t    cld admin resources max_results=10 -o tags=sample
# """)
# @argument("params", nargs=-1)
# @option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
# @option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
# @option("-ls", "--ls", is_flag=True, help="List all available functions in the Admin API")
# @option("--save", nargs=1, help="Save output to a file")
# @option("-d", "--doc", is_flag=True, help="Opens Admin API documentation page")
# def admin(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
#     if doc:
#         open_url("https://cloudinary.com/documentation/admin_api")
#         exit(0)
#     if ls or len(params) < 1:
#         print(get_help(api))
#         exit(0)
#     try:
#         func = api.__dict__[params[0]]
#         if not callable(func):
#             raise Exception(F_FAIL("{} is not callable.".format(func)))
#             exit(1)
#     except:
#         print(F_FAIL("Function {} does not exist in the Admin API.".format(params[0])))
#         exit(1)
#     parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
#     res = func(*parameters, **{
#         **options,
#         **{k:v for k,v in optional_parameter},
#         **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
#     })
#     log(res)
#     if save:
#         write_out(all_results, save)

# @command("uploader",
#          short_help="Upload API bindings",
#          help="""
# \b
# Upload API bindings
# format: cld uploader <function> <parameters> <optional_parameters>
# \teg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
# \b
# \teg. cld uploader rename flowers secret_flowers to_type=private
# \t      OR
# \t    cld uploader rename flowers secret_flowers -o to_type private
# """)
# @argument("params", nargs=-1)
# @option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
# @option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
# @option("-ls", "--ls", is_flag=True, help="List all available functions in the Upload API")
# @option("--save", nargs=1, help="Save output to a file")
# @option("-d", "--doc", is_flag=True, help="Opens Upload API documentation page")
# def uploader(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
#     if doc:
#         open_url("https://cloudinary.com/documentation/image_upload_api_reference")
#         exit(0)
#     if ls or len(params) < 1:
#         print(get_help(_uploader))
#         exit(0)
#     try:
#         func = _uploader.__dict__[params[0]]
#         if not callable(func):
#             raise Exception(F_FAIL("{} is not callable.".format(func)))
#             exit(1)
#     except:
#         print(F_FAIL("Function {} does not exist in the Upload API.".format(params[0])))
#         exit(1)
#     parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
#     res = func(*parameters, **{
#         **options,
#         **{k:v for k,v in optional_parameter},
#         **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
#     })
#     log(res)
#     if save:
#         write_out(res, save)


# @command("url", help="Generate a cloudinary url")
# @argument("public_id", required=True)
# @argument("transformation", default="")
# @option("-rt", "--resource_type", default="image", type=Choice(['image', 'video', 'raw']), help="Resource Type")
# @option("-t", "--type", default="upload", type=Choice(['upload', 'private', 'authenticated', 'fetch', 'list']), help="Type of the resource")
# @option("-o", "--open", is_flag=True, help="Open URL in your browser")
# @option("-s", "--sign", is_flag=True, help="Generates a signed URL", default=False)
# def url(public_id, transformation, resource_type, type, open, sign):
#     if type == "authenticated":
#         sign = True
#     elif type == "list":
#         public_id += ".json"
#     res = cld_url(public_id, resource_type=resource_type, raw_transformation=transformation, type=type, sign_url=sign)[0]
#     print(res)
#     if open:
#         open_url(res)


# @command("config", help="Display current configuration, and manage additional configurations")
# @option("-n", "--new", help="""\b Set an additional configuration
# eg. cld config -n <NAME> <CLOUDINARY_URL>""", nargs=2)
# @option("-ls", "--ls", help="List all configurations", is_flag=True)
# @option("-rm", "--rm", help="Delete an additional configuration", nargs=1)
# def config(new, ls, rm):
#     if not (new or ls or rm):
#         print('\n'.join(["{}:\t{}".format(k, v if k != "api_secret" else "***************{}".format(v[-4:])) for k, v in cloudinary._config.__dict__.items()]))
#         exit(0)

#     with open(CLOUDINARY_CLI_CONFIG_FILE, "r+") as f:
#         fi = f.read()
#         cfg = loads(fi) if fi != "" else {}
#         f.close()
#     if new:
#         try:
#             cloudinary._config._parse_cloudinary_url(new[1])
#             cfg[new[0]] = new[1]
#             api.ping()
#             with open(CLOUDINARY_CLI_CONFIG_FILE, "w") as f:
#                 f.write(dumps(cfg))
#                 f.close()
#             print("Config '{}' saved!".format(new[0]))
#         except:
#             print("Invalid Cloudinary URL: {}".format(new[1]))
#             exit(1)
#         exit(0)
#     if ls:
#         print("\n".join(cfg.keys()))
#         exit(0)
#     if rm:
#         if rm not in cfg.keys():
#             print("Configuration '{}' not found.".format(rm))
#             exit(1)
#         del cfg[rm]
#         open(CLOUDINARY_CLI_CONFIG_FILE, "w").write(dumps(cfg))
#         print("Configuration '{}' deleted".format(rm))
