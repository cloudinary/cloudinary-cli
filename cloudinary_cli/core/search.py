from ..utils import *
from webbrowser import open as open_url
from csv import DictWriter
from click import command, argument, option
from functools import reduce

@command("search",
         short_help="Search API Bindings",
         help="""\b
Search API bindings
format: cld search <Lucene query syntax string> <options>
eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10
""")
@argument("query", nargs=-1)
@option("-f", "--with_field", multiple=True, help="Field to include in result")
@option("-s", "--sort_by", nargs=2, help="Sort search results by (field, <asc|desc>)")
@option("-a", "--aggregate", nargs=1, help="Aggregation to apply to the query")
@option("-n", "--max_results", nargs=1, default=10, help="Maximum results to return. default: 10 max: 500")
@option("-c", "--next_cursor", nargs=1, help="Continue a search using an existing cursor")
@option("-A", "--auto_paginate", is_flag=True, help="Return all results. Will call Admin API multiple times.")
@option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate")
@option("-ff", "--filter_fields", multiple=True, help="Filter fields to return")
@option("--json", nargs=1, help="Save output as a JSON. Usage: --json <filename>")
@option("--csv", nargs=1, help="Save output as a CSV. Usage: --csv <filename>")
@option("-d", "--doc", is_flag=True, help="Opens Search API documentation page")
def search(query, with_field, sort_by, aggregate, max_results, next_cursor, auto_paginate, force, filter_fields, json, csv, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/search_api")
        exit(0)
    base_exp = cloudinary.search.Search().expression(" ".join(query))
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
        print("filtering")
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
            possible_keys = reduce(lambda x, y: set(y.keys()) | x, all_results, set())
            ff = list(possible_keys)
        writer = DictWriter(f, fieldnames=list(ff))

        writer.writeheader()
        writer.writerows(all_results)

        f.close()

        print('Saved search to \'{}.csv\''.format(csv))
        #write to csv
