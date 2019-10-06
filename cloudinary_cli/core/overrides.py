from click.parser import split_opt
from click.utils import make_str
from cloudinary import api, uploader
from cloudinary.uploader import call_cacheable_api
from cloudinary.utils import build_upload_params


# overrides click.MultiCommand.resolve_command
def resolve_command(self, ctx, args):
    cmd_name = make_str(args[0])
    original_cmd_name = cmd_name

    cmd = self.get_command(ctx, cmd_name)

    if cmd is None and ctx.token_normalize_func is not None:
        cmd_name = ctx.token_normalize_func(cmd_name)
        cmd = self.get_command(ctx, cmd_name)

    if cmd is None and not ctx.resilient_parsing:
        if split_opt(cmd_name)[0]:
            self.parse_args(ctx, ctx.args)

        if original_cmd_name in api.__dict__:
            cmd = self.get_command(ctx, "admin")
            return cmd_name, cmd, args
        elif original_cmd_name in uploader.__dict__:
            cmd = self.get_command(ctx, "uploader")
            return cmd_name, cmd, args
        else:
            ctx.fail('No such command "%s".' % original_cmd_name)

    return cmd_name, cmd, args[1:]


def upload(file, **options):
    params = build_upload_params(**options)
    if "resource_type" not in options.keys():
        options["resource_type"] = "auto"
    return call_cacheable_api("upload", params, file=file, **options)
