from webbrowser import open as open_url

from click import command, argument, option
from click.exceptions import UsageError
from cloudinary import uploader as _uploader

from cloudinary_cli.utils import logger, get_help, parse_args_kwargs, parse_option_value, write_out, log_json


@command("uploader",
         short_help="Run any methods that can be called through the upload API.",
         help="""
\b
Run any methods that can be called through the upload API.
Format: cld <cli options> uploader <command options> <method> <method parameters>
\te.g. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
\b
\te.g. cld uploader rename flowers secret_flowers to_type=private
\t      OR
\t    cld uploader rename flowers secret_flowers -o to_type private
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-ls", "--ls", is_flag=True, help="List all available methods in the Upload API.")
@option("--save", nargs=1, help="Save output to a file.")
@option("-d", "--doc", is_flag=True, help="Open the Upload API reference in a browser.")
def uploader(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/image_upload_api_reference")
        return
    if ls or len(params) < 1:
        logger.info(get_help(_uploader))
        return
    try:
        func = _uploader.__dict__[params[0]]
        if not callable(func):
            raise UsageError("{} is not callable.".format(func))
    except Exception as e:
        raise e
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **{
        **options,
        **{k: v for k, v in optional_parameter},
        **{k: parse_option_value(v) for k, v in optional_parameter_parsed},
    })
    log_json(res)
    if save:
        write_out(res, save)
