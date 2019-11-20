from webbrowser import open as open_url

import cloudinary
from click import command, argument, option
from cloudinary.utils import cloudinary_url


@command("sample", help="Open sample flowers image", hidden=True)
@argument("transformation", default="")
@option("-o", "--open", is_flag=True, help="Open URL in your browser")
def sample(transformation, open):
    cloudinary.config(cloud_name="demo", secure_distribution=None, cname=None)
    res = cloudinary_url('sample', raw_transformation=transformation)[0]
    print(res)
    if open:
        open_url(res)


@command("couple", help="Open sample couple image", hidden=True)
@argument("transformation", default="")
@option("-o", "--open", is_flag=True, help="Open URL in your browser")
def couple(transformation, open):
    cloudinary.config(cloud_name="demo", secure_distribution=None, cname=None)
    res = cloudinary_url('couple', raw_transformation=transformation)[0]
    print(res)
    if open:
        open_url(res)


@command("dog", help="Open sample dog video", hidden=True)
@argument("transformation", default="")
@option("-o", "--open", is_flag=True, help="Open URL in your browser")
def dog(transformation, open):
    cloudinary.config(cloud_name="demo", secure_distribution=None, cname=None)
    res = cloudinary_url('dog', raw_transformation=transformation, resource_type="video")[0]
    print(res)
    if open:
        open_url(res)


def import_commands(cli):
    cli.add_command(sample)
    cli.add_command(couple)
    cli.add_command(dog)
