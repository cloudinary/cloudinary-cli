from click import command, argument, option
from cloudinary_cli.utils.utils import print_help_and_exit
from cloudinary_cli.utils.api_utils import handle_api_command, regen_derived_version
from cloudinary import api
from cloudinary_cli.utils.utils import confirm_action, run_tasks_concurrently
from cloudinary_cli.defaults import logger

DEFAULT_MAX_RESULTS = 500

@command("regen_derived",
         short_help="""Regenerate all derived of a transformation.""",
         help="""
\b
Regenerate all derived versions of a named transformations.
Format: cld regen_dervied <transformation_name> <command options>
e.g. cld regen_derived t_named -A -ea -enu http://mywebhook.com
""")
@argument("trans_str")
@option("-enu", "--eager_notification_url", help="Webhook notification URL.")
@option("-ea", "--eager_async", is_flag=True, default=False,
        help="Generate asynchronously.")
@option("-A", "--auto_paginate", is_flag=True, default=False,
        help="Will auto paginate Admin API calls.")
@option("-F", "--force", is_flag=True,
        help="Skip confirmation when running --auto-paginate/-A.")
@option("-n", "--max_results", nargs=1, default=10,
        help="""The maximum number of derived results to return.
              Default: 10, maximum: 500.""")
@option("-w", "--concurrent_workers", type=int, default=30,
        help="Specify the number of concurrent network threads.")
def regen_derived(trans_str, eager_notification_url,
                  eager_async, auto_paginate, force,
                  max_results, concurrent_workers):

    if not any(trans_str):
        print_help_and_exit()

    if not force:
        if not confirm_action(
            f"Running this module will explicity "
            f"re-generate all the related derived versions "
            f"which will cause an increase in your transformation costs "
            f"based on the number of derived re-generated.\n"
            f"If running in auto_paginate (-A) mode, "
            f"multiple Admin API (rate-limited) calls will be used as well.\n"
            f"Continue? (y/N)"):
            logger.info("Stopping.")
            exit()
        else:
            logger.info("Continuing. You may use the -F "
                        "flag to skip confirmation.")

    if auto_paginate:
        max_results = DEFAULT_MAX_RESULTS
        force = True

    params = ('transformation', trans_str, f'max_results={max_results}')
    trans_details = handle_api_command(params, (), (), None, None, None,
                                       doc_url="", api_instance=api,
                                       api_name="admin",
                                       auto_paginate=auto_paginate,
                                       force=force, return_data=True)
    derived_resources = trans_details.get('derived')
    if not derived_resources:
        logger.info("No derived resources using this transformation.")
        exit()

    is_named = trans_details.get('named')
    if is_named:
        eager_trans = normalise_trans_name(trans_str)

    progress_msg = f"Regenerating {len(derived_resources)} derived version(s)"
    if eager_async:
        logger.info(f"{progress_msg} "
                    f"with eager_async={eager_async}...")
    else:
        logger.info(f"{progress_msg}...")

    regen_conc_list = []
    for derived in derived_resources:
        public_id = derived.get('public_id')
        delivery_type = derived.get('type')
        res_type = derived.get('resource_type')
        options = {"type": delivery_type, "resource_type": res_type,
                   "eager": eager_trans, "eager_async": eager_async,
                   "eager_notification_url": eager_notification_url,
                   "overwrite": True, "invalidate": True}
        regen_conc_list.append((public_id, options))

    run_tasks_concurrently(regen_derived_version, regen_conc_list,
                           concurrent_workers)

    logger.info("Regen complete. It may take up to 10 mins "
                "to see the changes. Please contact support "
                "if you still see the old media.")
    return True


def normalise_trans_name(trans_name):
    normalised_trans_name = trans_name
    if not normalised_trans_name.startswith('t_'):
        normalised_trans_name = 't_' + normalised_trans_name
    return normalised_trans_name
