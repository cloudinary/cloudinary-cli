from webbrowser import open as open_url

from cloudinary_cli.utils import parse_args_kwargs, parse_option_value, log_json, write_out, print_help


def handle_api_command(
        params,
        optional_parameter,
        optional_parameter_parsed,
        ls,
        save,
        doc,
        doc_url,
        api_instance,
        api_name):
    if doc:
        return open_url(doc_url)

    if ls or len(params) < 1:
        return print_help(api_instance)

    try:
        func = api_instance.__dict__[params[0]]
        if not callable(func):
            raise Exception(f"{func} is not callable")
    except Exception:
        raise Exception(f"Method {params[0]} does not exist in the {api_name.capitalize()} API.")

    args, kwargs = parse_args_kwargs(func, params[1:]) if len(params) > 1 else ([], {})

    res = func(*args, **{
        **kwargs,
        **{k: v for k, v in optional_parameter},
        **{k: parse_option_value(v) for k, v in optional_parameter_parsed},
    })

    log_json(res)

    if save:
        write_out(res, save)
