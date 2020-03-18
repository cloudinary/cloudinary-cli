from webbrowser import open as open_url

from click import command, argument, option
from cloudinary import api

from cloudinary_cli.utils import get_help, parse_args_kwargs, parse_option_value, log_json, write_out, logger


@command("admin",
         short_help="Run any methods that can be called through the admin API.",
         help="""\b
Run any methods that can be called through the admin API.
Format: cld <cli options> admin <command options> <method> <method parameters>
\te.g. cld admin resources max_results=10 tags=sample
\t      OR
\t    cld admin resources -o max_results 10 -o tags sample
\t      OR
\t    cld admin resources max_results=10 -o tags sample
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-ls", "--ls", is_flag=True, help="List all available methods in the Admin API.")
@option("--save", nargs=1, help="Save output to a file.")
@option("-d", "--doc", is_flag=True, help="Open the Admin API reference in a browser.")
def admin(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/admin_api")
        return
    if ls or len(params) < 1:
        logger.info(get_help(api))
        return
    try:
        func = api.__dict__[params[0]]
        if not callable(func):
            raise Exception("{} is not callable".format(func))
    except Exception:
        raise Exception("Method {} does not exist in the Admin API.".format(params[0]))
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **{
        **options,
        **{k: v for k, v in optional_parameter},
        **{k: parse_option_value(v) for k, v in optional_parameter_parsed},
    })
    log_json(res)
    if save:
        write_out(res, save)
