from click import command, argument, option
from cloudinary_cli.utils.utils import print_help_and_exit
from cloudinary_cli.utils.api_utils import handle_api_command, regen_derived_version
from cloudinary import api
from cloudinary_cli.utils.utils import confirm_action, run_tasks_concurrently
from cloudinary_cli.defaults import logger

DEFAULT_MAX_RESULTS = 500


@command("regen_derived",
         short_help="""Regenerate all derived assets pertaining \
         to a named transformation, or transformation string.""",
         help="""
\b
Regenerate all derived assets pertaining to a specific named transformation, or transformation string.
Use this after updating a named transformation to invalidate and repopulate the cache with up-to-date versions of the assets.
Format: cld regen_derived <transformation_name> <command options>
e.g. cld regen_derived t_named -A -ea -enu http://mywebhook.com
""")
@argument("trans_str")
@option("-enu", "--eager_notification_url", help="Webhook notification URL.")
@option("-ea", "--eager_async", is_flag=True, default=False,
        help="Generate asynchronously.")
@option("-A", "--auto_paginate", is_flag=True, default=False,
        help="Auto-paginate Admin API calls.")
@option("-F", "--force", is_flag=True,
        help="Skip initial and auto-paginate confirmation.")
@option("-n", "--max_results", nargs=1, default=10,
        help="""The maximum number of results to return.
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
            f"re-generate all the related derived assets "
            f"which will cause an increase in your transformation costs "
            f"based on the number of derived assets re-generated.\n"
            f"If running in auto-paginate (-A) mode, "
            f"multiple Admin API (rate-limited) calls will be made.\n"
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
        logger.info("No derived assets are using this transformation.")
        exit()

    is_named = trans_details.get('named')
    eager_trans = normalise_trans_name(trans_str) if is_named else trans_str

    progress_msg = f"Regenerating {len(derived_resources)} derived asset(s)"
    if eager_async:
        progress_msg += f" with eager_async={eager_async}"
    logger.info(f"{progress_msg}...")

    regen_conc_list = []
    for derived in derived_resources:
        public_id = derived.get('public_id')
        delivery_type = derived.get('type')
        res_type = derived.get('resource_type')
        regen_conc_list.append((public_id, delivery_type, res_type,
                                eager_trans, eager_async,
                                eager_notification_url))

    run_tasks_concurrently(regen_derived_version, regen_conc_list,
                           concurrent_workers)
    complete_msg = ('Regeneration in progress'
                    if eager_async else 'Regeneration complete')
    logger.info(f"{complete_msg}. It may take up to 10 mins "
                "to see the changes. Please contact support "
                "if you still see the old media.")
    return True


def normalise_trans_name(trans_name):
    return trans_name if trans_name.startswith('t_') else 't_' + trans_name
