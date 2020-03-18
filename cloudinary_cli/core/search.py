import json as _json
import tempfile
from csv import DictWriter
from functools import reduce
from webbrowser import open as open_url

import cloudinary
from click import command, argument, option

from cloudinary_cli.utils import logger, log_json, write_out


@command("search",
         short_help="Run the admin API search method.",
         help="""\b
Run the admin API search method.
Format: cld <cli options> search <command options> <Lucene query syntax string>
e.g. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10
""")
@argument("query", nargs=-1)
@option("-f", "--with_field", multiple=True, help="Specify which asset attribute to include in the result.")
@option("-s", "--sort_by", nargs=2, help="Sort search results by (field, <asc|desc>).")
@option("-a", "--aggregate", nargs=1, help="Specify the attribute for which an aggregation count should be calculated and returned.")
@option("-n", "--max_results", nargs=1, default=10, help="The maximum number of results to return. Default: 10, maximum: 500.")
@option("-c", "--next_cursor", nargs=1, help="Continue a search using an existing cursor.")
@option("-A", "--auto_paginate", is_flag=True, help="Return all results. Will call Admin API multiple times.")
@option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate.")
@option("-ff", "--filter_fields", multiple=True, help="Filter fields to return.")
@option("--json", nargs=1, help="Save JSON output to a file. Usage: --json <filename>")
@option("--csv", nargs=1, help="Save CSV output to a file. Usage: --csv <filename>")
@option("-d", "--doc", is_flag=True, help="Open Search API documentation page.")
def search(query, with_field, sort_by, aggregate, max_results, next_cursor,
           auto_paginate, force, filter_fields, json, csv, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/search_api")
        return
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
            r = input("{} total results. {} Admin API rate limit remaining.\n"
                      "Running this program will use {} Admin API calls. Continue? (Y/N) ".format(
                res['total_count'],
                res.__dict__['rate_limit_remaining'] + 1,
                res['total_count'] // 500 + 1))
            if r.lower() != 'y':
                logger.info("Exiting. Please run again without -A.")
                return
            else:
                logger.info("Continuing. You may use the -F flag to force auto_pagination.")

        with tempfile.TemporaryFile(mode="w+b") as tmp_file:
            tmp_file.write(bytes(_json.dumps(res['resources']) + "\n", encoding="utf8"))

            while 'next_cursor' in res.keys():
                # stream output to file
                exp = base_exp.next_cursor(res['next_cursor'])
                res = exp.execute()
                tmp_file.write(bytes(_json.dumps(res['resources']) + "\n", encoding="utf8"))

            all_results['resources'] = []
            tmp_file.seek(0)

            for line in tmp_file:
                if line:
                    all_results['resources'] += _json.loads(line.decode('utf8'))

    return_fields = []
    if filter_fields:
        for f in list(filter_fields):
            if "," in f:
                return_fields += f.split(",")
            else:
                return_fields.append(f)
        return_fields = tuple(return_fields) + with_field
        all_results['resources'] = list(map(lambda x: {k: x[k] if k in x.keys()
        else None for k in return_fields}, all_results['resources']))

    log_json(all_results)

    if json:
        write_out(all_results['resources'], json)

    if csv:
        all_results = all_results['resources']
        f = open('{}.csv'.format(csv), 'w')
        if not return_fields:
            possible_keys = reduce(lambda x, y: set(y.keys()) | x, all_results, set())
            return_fields = list(possible_keys)
        writer = DictWriter(f, fieldnames=list(return_fields))

        writer.writeheader()
        writer.writerows(all_results)

        f.close()

        logger.info('Saved search to \'{}.csv\''.format(csv))
