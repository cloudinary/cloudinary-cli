from ..utils import *
from webbrowser import open as open_url
from csv import DictWriter
from cloudinary.utils import cloudinary_url as cld_url
from cloudinary import api, uploader as _uploader
from click import command, argument, option, Choice


@command("admin",
         short_help="Admin API bindings",
         help="""\b
Admin API bindings
format: cld admin <function> <parameters> <optional_parameters>
\teg. cld admin resources max_results=10 tags=sample
\t      OR
\t    cld admin resources -o max_results 10 -o tags sample
\t      OR
\t    cld admin resources max_results=10 -o tags=sample
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@option("-ls", "--ls", is_flag=True, help="List all available functions in the Admin API")
@option("--save", nargs=1, help="Save output to a file")
@option("-d", "--doc", is_flag=True, help="Opens Admin API documentation page")
def admin(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/admin_api")
        exit(0)
    if ls or len(params) < 1:
        print(get_help(api))
        exit(0)
    try:
        func = api.__dict__[params[0]]
        if not callable(func):
            raise Exception(F_FAIL("{} is not callable.".format(func)))
            exit(1)
    except:
        print(F_FAIL("Function {} does not exist in the Admin API.".format(params[0])))
        exit(1)
    parameters, options = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})
    res = func(*parameters, **{
        **options,
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
    })
    log(res)
    if save:
        write_out(res, save)