from click import command, argument, option
from cloudinary_cli.utils.utils import print_help_and_exit
from cloudinary import uploader as upload_api
from cloudinary_cli.utils.api_utils import handle_module_command, handle_command
from cloudinary import api
from cloudinary_cli.utils.utils import confirm_action
from cloudinary_cli.defaults import logger
import logging
from datetime import datetime

DEFAULT_MAX_RESULTS = 500

curr_dt = datetime.today().strftime('%Y-%m-%d')
filename = f'regenerate_derived_public_ids_{curr_dt}.log'
logging.basicConfig(filename=filename,
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s - %(message)s')


@command("regenerate_all_derived_by_transformation",
         short_help="""Regenerate all derived of a transformation.""",
         help="""
\b
Regenerate all derived versions of a named transformations.
Format: cld regenerate_all_derived_by_transformation <transformation_name> <command options>
e.g. cld regenerate_all_derived_by_transformation t_named -A -ea -enu http://mywebhook.com
""")
@argument("trans_str")
@option("-enu", "--eager_notification_url", help="Webhook notification URL.")
@option("-ea", "--eager_async", is_flag=True, default=False,
        help="Generate asynchronously.")
@option("-A", "--auto_paginate", is_flag=True, default=False,
        help="Will auto paginate Admin API calls.")
@option("-F", "--force", is_flag=True,
        help="Skip confirmation when running --auto-paginate/-A.")
@option("-fi", "--force_initial", is_flag=True,
        help="Skip initial confirmation when running this module.")
@option("-n", "--max_results", nargs=1, default=10,
        help="""The maximum number of derived results to return.
              Default: 10, maximum: 500.""")
def regenerate_all_derived_by_transformation(trans_str, eager_notification_url,
                                         eager_async, auto_paginate, force,
                                         force_initial, max_results):
    if not any(trans_str):
        print_help_and_exit()

    if not force_initial:
        if not confirm_action(
            f"Running this module will explicity "
            f"re-generate all the derived versions "
            f"which will cause an increase in your transformation costs "
            f"based on the number of derived re-generated.\n"
            f"Continue? (y/N)"):
            logger.info("Stopping.")
            exit()
        else:
            logger.info("Continuing. You may use the -fi "
                        "flag to skip initial confirmation.")

    if auto_paginate:
        max_results = DEFAULT_MAX_RESULTS

    params = ('transformation', trans_str, f'max_results={max_results}')
    res = handle_module_command(params, (), (), api_instance=api,
                                api_name="admin", auto_paginate=auto_paginate,
                                force=force)

    if res:
        eager_trans = trans_str
        is_named = res.get('named')
        if is_named:
            if not eager_trans.startswith('t_'):
                eager_trans = 't_' + eager_trans
        logger.info(f"Regenerating {len(res.get('derived'))} derived versions "
                    f"with eager_async={eager_async}...\n"
                    f"Output is saved in {filename}")
        for derived in res.get('derived'):
            public_id = derived.get('public_id')
            delivery_type = derived.get('type')
            res_type = derived.get('resource_type')
            params = ('explicit', public_id, f'type={delivery_type}',
                      f'resource_type={res_type}', f'eager={eager_trans}',
                      f'eager_async={eager_async}',
                      f'eager_notification_url={eager_notification_url}',
                      'overwrite=True', 'invalidate=True')

            try:
                exp_res = handle_command(params, (), (), module=upload_api,
                                         module_name="regenerate_all_derived_by_transformation")
            except Exception as e:
                error_data = (f'public_id={public_id}, type={delivery_type}, '
                              f'resource_type={res_type}: {e}')
                logging.error(error_data)
                continue

            if eager_async:
                msg = f'Processing {exp_res.get("eager")[0].get("secure_url")}'
            else:
                msg = f'Generated {exp_res.get("eager")[0].get("secure_url")}'

            logging.info(msg)
        logger.info("Please contact support if you do not see "
                    "updated derived versions after running this. "
                    "Do not re-run or it will cost more.")

    return True
