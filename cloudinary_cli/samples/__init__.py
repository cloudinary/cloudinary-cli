import cloudinary
from click import command, argument, option, launch
from cloudinary.utils import cloudinary_url


@command("sample", help="Open sample flowers image", hidden=True)
@argument("transformation", default="")
@option("-o", "--open", 'open_in_browser', is_flag=True, help="Open URL in your browser", )
def sample(transformation, open_in_browser):
    return _handle_sample_command("sample", transformation, open_in_browser)


@command("couple", help="Open sample couple image", hidden=True)
@argument("transformation", default="")
@option("-o", "--open", 'open_in_browser', is_flag=True, help="Open URL in your browser")
def couple(transformation, open_in_browser):
    return _handle_sample_command("couple", transformation, open_in_browser)


@command("dog", help="Open sample dog video", hidden=True)
@argument("transformation", default="")
@option("-o", "--open", 'open_in_browser', is_flag=True, help="Open URL in your browser")
def dog(transformation, open_in_browser):
    return _handle_sample_command("dog", transformation, open_in_browser, "video")


def _handle_sample_command(source, transformation=None, open_in_browser=False, resource_type="image"):
    cloudinary.config(cloud_name="demo", secure_distribution=None, cname=None)
    res = cloudinary_url(source, raw_transformation=transformation, resource_type=resource_type)
    print(res)
    if open_in_browser:
        launch(res)


commands = [
    sample,
    couple,
    dog,
]
