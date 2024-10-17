from typing import List, Optional, Tuple, Any
from click import command, argument, option, launch

@command("search",
         short_help="Run the admin API search method.",
         help="""\b
Run the admin API search method.
Format: cld <cli options> search <command options> <Lucene query syntax string>
e.g. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10
""")
@argument("query", nargs=-1)
@option("-f", "--with_field", multiple=True, help="Specify which non-default asset attributes to include "
                                                  "in the result as a comma separated list. ")
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
@option("-t", "--ttl", nargs=1, default=300, help="Set the Search URL TTL in seconds. Default: 300.")
@option("-u", "--url", is_flag=True, help="Build a signed search URL.")
@option("-sq", "--search-query", is_flag=True, help="Show the search request query.", hidden=True)
@option("--json", nargs=1, help="Save JSON output to a file. Usage: --json <filename>")
@option("--csv", nargs=1, help="Save CSV output to a file. Usage: --csv <filename>")
@option("-d", "--doc", is_flag=True, help="Open Search API documentation page.")
def search(
    query: Tuple[str, ...],
    with_field: List[str],
    fields: List[str],
    sort_by: Optional[Tuple[str, str]],
    aggregate: Optional[str],
    max_results: str,
    next_cursor: Optional[str],
    auto_paginate: bool,
    force: bool,
    filter_fields: List[str],
    ttl: str,
    url: bool,
    search_query: bool,
    json: Optional[str],
    csv: Optional[str],
    doc: bool
) -> None:
    ...

def execute_single_request(expression: Any, fields_to_keep: Tuple[str, ...]) -> Any:
    ...

def handle_auto_pagination(res: Any, expression: Any, force: bool, fields_to_keep: Tuple[str, ...]) -> Any:
    ...
