from click.parser import split_opt
from click.utils import make_str
from cloudinary import api, uploader
from cloudinary.uploader import upload as original_upload
from cloudinary.utils import cloudinary_url as original_cloudinary_url


# overrides click.MultiCommand.resolve_command
def resolve_command(self, ctx, args):
    # Patch the `resolve_command` function to enable simple commands (eg. cld resource)
    # Only core commands from API and modules are registered (eg. cld admin)
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


# Patch to set `auto` resource type
def upload(file, **options):
    """
    Uploads an asset to a Cloudinary cloud.

    The asset can be:
       * a local file path
       * the actual data (byte array buffer)
       * the Data URI (Base64 encoded), max ~60 MB (62,910,000 chars)
       * the remote FTP, HTTP or HTTPS URL address of an existing file
       * a private storage bucket (S3 or Google Storage) URL of a whitelisted bucket

    See: https://cloudinary.com/documentation/image_upload_api_reference#upload_method
    :param file: The asset to upload.
    :type file: Any or str
    :param options: The optional parameters. See the upload API documentation.
    :type options: dict, optional
    :return: The result of the upload API call.
    :rtype: dict
    """
    if "resource_type" not in options.keys():
        options["resource_type"] = "auto"
    return original_upload(file, **options)


# Patch to return only the URL
def cloudinary_url(source, **options):
    return original_cloudinary_url(source, **options)[0]
