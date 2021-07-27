from os import getcwd, walk
from os.path import dirname, split, join as path_join, abspath

from click import command, argument, option, style

from cloudinary_cli.utils.api_utils import upload_file
from cloudinary_cli.utils.utils import parse_option_value, logger, run_tasks_concurrently
from cloudinary_cli.utils.file_utils import get_destination_folder


@command("upload_dir", help="""Upload a folder of assets, maintaining the folder structure.""")
@argument("directory", default=".")
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed",
        multiple=True,
        nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-t", "--transformation", help="The transformation to apply on all uploads.")
@option("-f", "--folder", default="",
        help="The Cloudinary folder where you want to upload the assets. "
             "You can specify a whole path, for example folder1/folder2/folder3. "
             "Any folders that do not exist are automatically created.")
@option("-p", "--preset", help="The upload preset to use.")
@option("-w", "--concurrent_workers", type=int, default=30, help="Specify number of concurrent network threads.")
def upload_dir(directory, optional_parameter, optional_parameter_parsed, transformation, folder, preset,
               concurrent_workers):
    items, skipped = {}, {}
    dir_to_upload = abspath(path_join(getcwd(), directory))
    logger.info("Uploading directory '{}'".format(dir_to_upload))
    parent = dirname(dir_to_upload)
    options = {
        **{k: v for k, v in optional_parameter},
        **{k: parse_option_value(v) for k, v in optional_parameter_parsed},
        "resource_type": "auto",
        "invalidate": True,
        "unique_filename": False,
        "use_filename": True,
        "raw_transformation": transformation,
        "upload_preset": preset
    }

    uploads = []

    for root, _, files in walk(dir_to_upload):
        for fi in files:
            file_path = abspath(path_join(dir_to_upload, root, fi))

            if split(file_path)[1][0] == ".":
                continue

            options = {**options, "folder": get_destination_folder(folder, file_path, parent=parent)}
            uploads.append((file_path, options, items, skipped))

    run_tasks_concurrently(upload_file, uploads, concurrent_workers)

    logger.info(style("{} resources uploaded".format(len(items)), fg="green"))
    if skipped:
        logger.warn("{} items skipped".format(len(skipped)))
