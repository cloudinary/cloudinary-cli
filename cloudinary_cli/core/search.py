from webbrowser import open as open_url

import cloudinary
from click import command, argument, option

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.json_utils import write_json_to_file, print_json
from cloudinary_cli.utils.utils import write_json_list_to_csv, confirm_action, whitelist_keys, \
    normalize_list_params

DEFAULT_MAX_RESULTS = 500


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
@option("-a", "--aggregate", nargs=1,
        help="Specify the attribute for which an aggregation count should be calculated and returned.")
@option("-n", "--max_results", nargs=1, default=10,
        help="The maximum number of results to return. Default: 10, maximum: 500.")
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
        return open_url("https://cloudinary.com/documentation/search_api")

    fields_to_keep = []
    if filter_fields:
        fields_to_keep = tuple(normalize_list_params(filter_fields)) + with_field

    expression = cloudinary.search.Search().expression(" ".join(query))

    if auto_paginate:
        max_results = DEFAULT_MAX_RESULTS
    if with_field:
        for f in with_field:
            expression.with_field(f)
    if sort_by:
        expression.sort_by(*sort_by)
    if aggregate:
        expression.aggregate(aggregate)
    if next_cursor:
        expression.next_cursor(next_cursor)

    expression.max_results(max_results)

    res = execute_single_request(expression, fields_to_keep)

    if auto_paginate:
        res = handle_auto_pagination(res, expression, force, fields_to_keep)

    print_json(res)

    if json:
        write_json_to_file(res['resources'], json)
        logger.info(f"Saved search JSON to '{json}' file")

    if csv:
        write_json_list_to_csv(res['resources'], csv, fields_to_keep)
        logger.info(f"Saved search to '{csv}.csv' file")


def execute_single_request(expression, fields_to_keep):
    res = expression.execute()

    if fields_to_keep:
        res['resources'] = whitelist_keys(res['resources'], fields_to_keep)

    return res


def handle_auto_pagination(res, expression, force, fields_to_keep):
    if 'next_cursor' not in res:
        return res

    if not force:
        if not confirm_action(
                f"{res['total_count']} total results. "
                f"{res.rate_limit_remaining + 1} Admin API rate limit remaining.\n"
                f"Running this query will use {res['total_count'] // DEFAULT_MAX_RESULTS + 1} Admin API calls. "
                f"Continue? (y/N)"):
            logger.info("Stopping. Please run again without -A.")

            return res
        else:
            logger.info("Continuing. You may use the -F flag to force auto_pagination.")

    all_results = res
    while 'next_cursor' in res.keys():
        expression.next_cursor(res['next_cursor'])

        res = execute_single_request(expression, fields_to_keep)

        all_results['resources'] += res['resources']
        all_results['time'] += res['time']

    all_results.pop('next_cursor', None)  # it is empty by now

    return all_results
