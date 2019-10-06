from ..utils import *
from webbrowser import open as open_url
from cloudinary import uploader as _uploader
from click import command, argument, option


@command("uploader",
         short_help="Upload API bindings",
         help="""
\b
Upload API bindings
format: cld uploader <function> <parameters> <optional_parameters>
\teg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
\b
\teg. cld uploader rename flowers secret_flowers to_type=private
\t      OR
\t    cld uploader rename flowers secret_flowers -o to_type private
""")
@argument("params", nargs=-1)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@option("-ls", "--ls", is_flag=True, help="List all available functions in the Upload API")
@option("--save", nargs=1, help="Save output to a file")
@option("-d", "--doc", is_flag=True, help="Opens Upload API documentation page")
def uploader(params, optional_parameter, optional_parameter_parsed, ls, save, doc):
    if doc:
        open_url("https://cloudinary.com/documentation/image_upload_api_reference")
        exit(0)
    if ls or len(params) < 1:
        print(get_help(_uploader))
        exit(0)
    try:
        func = _uploader.__dict__[params[0]]
        if not callable(func):
            raise Exception(F_FAIL("{} is not callable.".format(func)))
            exit(1)
    except:
        print(F_FAIL("Function {} does not exist in the Upload API.".format(params[0])))
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

