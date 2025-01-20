import cloudinary
from click import command, argument, option, launch
from functools import wraps

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.json_utils import write_json_to_file, print_json
from cloudinary_cli.utils.utils import write_json_list_to_csv, confirm_action, whitelist_keys, \
    normalize_list_params

DEFAULT_MAX_RESULTS = 500


def shared_options(func):
    @option("-f", "--with_field", multiple=True, help="Specify which non-default asset attributes to include "
                                                      "in the result as a comma separated list.")
    @option("-fi", "--fields", multiple=True, help="Specify which asset attributes to include in the result "
                                                   "(together with a subset of the default attributes) as a comma separated"
                                                   " list. This overrides any value specified for with_field.")
    @option("-s", "--sort_by", nargs=2, help="Sort search results by (field, <asc|desc>).")
    @option("-a", "--aggregate", nargs=1,
            help="Specify the attribute for which an aggregation count should be calculated and returned.")
    @option("-n", "--max_results", nargs=1, default=10,
            help="The maximum number of results to return. Default: 10, maximum: 500.")
    @option("-c", "--next_cursor", nargs=1, help="Continue a search using an existing cursor.")
    @option("-A", "--auto_paginate", is_flag=True, help="Return all results. Will call Admin API multiple times.")
    @option("-F", "--force", is_flag=True, help="Skip confirmation when running --auto-paginate.")
    @option("-ff", "--filter_fields", multiple=True, help="Specify which attributes to show in the response. "
                                                          "None of the others will be shown.")
    @option("-sq", "--search-query", is_flag=True, help="Show the search request query.", hidden=True)
    @option("--json", nargs=1, help="Save JSON output to a file. Usage: --json <filename>")
    @option("--csv", nargs=1, help="Save CSV output to a file. Usage: --csv <filename>")
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


@command("search",
         short_help="Run the Admin API search method.",
         help="""\b
Run the Admin API search method.
Format: cld <cli options> search <command options> <Lucene query syntax string>
e.g. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10
""")
@argument("query", nargs=-1)
@shared_options
@option("-t", "--ttl", nargs=1, default=300, help="Set the Search URL TTL in seconds. Default: 300.")
@option("-u", "--url", is_flag=True, help="Build a signed search URL.")
@option("-d", "--doc", is_flag=True, help="Open Search API documentation page.")
def search(query, with_field, fields, sort_by, aggregate, max_results, next_cursor,
           auto_paginate, force, filter_fields, ttl, url, search_query, json, csv, doc):
    search_instance = cloudinary.search.Search()
    doc_url = "https://cloudinary.com/documentation/search_api"
    result_field = 'resources'
    return _perform_search(query, with_field, fields, sort_by, aggregate, max_results, next_cursor,
                           auto_paginate, force, filter_fields, ttl, url, search_query, json, csv, doc,
                           search_instance, doc_url, result_field)


@command("search_folders",
         short_help="Run the Admin API search folders method.",
         help="""\b
Run the Admin API search folders method.
Format: cld <cli options> search_folders <command options> <Lucene query syntax string>
e.g. cld search_folders name:folder AND path:my_parent AND created_at>4w
""")
@argument("query", nargs=-1)
@shared_options
@option("-d", "--doc", is_flag=True, help="Open Search Folders API documentation page.")
def search_folders(query, with_field, fields, sort_by, aggregate, max_results, next_cursor,
                   auto_paginate, force, filter_fields, search_query, json, csv, doc):
    search_instance = cloudinary.search_folders.SearchFolders()
    doc_url = "https://cloudinary.com/documentation/admin_api#search_folders"
    result_field = 'folders'
    return _perform_search(query, with_field, fields, sort_by, aggregate, max_results, next_cursor,
                           auto_paginate, force, filter_fields, 300, False, search_query, json, csv, doc,
                           search_instance, doc_url, result_field)


def _perform_search(query, with_field, fields, sort_by, aggregate, max_results, next_cursor,
                    auto_paginate, force, filter_fields, ttl, url, search_query, json, csv, doc,
                    search_instance, doc_url, result_field):
    """Shared logic for running a search."""
    if doc:
        return launch(doc_url)

    fields_to_keep = []
    if filter_fields:
        fields_to_keep = tuple(normalize_list_params(filter_fields)) + tuple(normalize_list_params(with_field))

    search = search_instance.expression(" ".join(query))

    if auto_paginate:
        max_results = DEFAULT_MAX_RESULTS
    if with_field:
        search.with_field(normalize_list_params(with_field))
    if fields:
        search.fields(normalize_list_params(fields))
    if sort_by:
        search.sort_by(*sort_by)
    if aggregate:
        search.aggregate(aggregate)
    if next_cursor:
        search.next_cursor(next_cursor)
    if ttl:
        search.ttl(ttl)

    search.max_results(max_results)

    if url:
        print(search.to_url())
        return True

    if search_query:
        print_json(search.as_dict())
        return True

    res = execute_single_request(search, fields_to_keep, result_field)

    if auto_paginate:
        res = handle_auto_pagination(res, search, force, fields_to_keep, result_field)

    print_json(res)

    if json:
        write_json_to_file(res[result_field], json)
        logger.info(f"Saved search JSON to '{json}' file")

    if csv:
        write_json_list_to_csv(res[result_field], csv, fields_to_keep)
        logger.info(f"Saved search to '{csv}.csv' file")


def execute_single_request(expression, fields_to_keep, result_field='resources'):
    res = expression.execute()

    if fields_to_keep:
        res[result_field] = whitelist_keys(res[result_field], fields_to_keep)

    return res


def handle_auto_pagination(res, expression, force, fields_to_keep, result_field='resources'):
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

        res = execute_single_request(expression, fields_to_keep, result_field)

        all_results[result_field] += res[result_field]
        all_results['time'] += res['time']

    all_results.pop('next_cursor', None)  # it is empty by now

    return all_results
