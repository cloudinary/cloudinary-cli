from os import getcwd
from os.path import dirname, join as path_join
from pathlib import Path

from click import command, argument, option, style, launch, Choice

from cloudinary_cli.utils.api_utils import upload_file, get_default_upload_options, get_folder_mode, \
    get_destination_folder_options
from cloudinary_cli.utils.file_utils import get_destination_folder, is_hidden_path
from cloudinary_cli.utils.utils import parse_option_value, logger, run_tasks_concurrently, group_params


@command("upload_dir", help="""Upload a folder of assets, maintaining the folder structure.""")
@argument("directory", default=".")
@option("-g", "--glob-pattern", default="**/*", help="The glob pattern. "
                                                     "For example use '**/*.jpg' to upload only jpg files.")
@option("-H", "--include-hidden", is_flag=True, help="Include hidden files.")
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed",
        multiple=True,
        nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-t", "--transformation", help="The transformation to apply on all uploads.")
@option("-f", "--folder", default="",
        help="The path where you want to upload the assets. "
             "The path you specify will be pre-pended to the public IDs of the uploaded assets. "
             "You can specify a whole path, for example path1/path2/path3. "
             "Any folders that do not exist are automatically created.")
@option("-fm", "--folder-mode", type=Choice(['fixed', 'dynamic'], case_sensitive=False),
        help="Specify folder mode explicitly. By default uses cloud mode configured in your cloud.", hidden=True)
@option("-p", "--preset", help="The upload preset to use.")
@option("-e", "--exclude-dir-name", is_flag=True, default=False,
        help="When this option is used, the contents of the parent directory are uploaded but not the parent "
             "directory itself. Thus, the name of the specified parent directory is not included "
             "in the pubic ID path of the uploaded assets.")
@option("-w", "--concurrent_workers", type=int, default=30, help="Specify the number of concurrent network threads.")
@option("-d", "--doc", is_flag=True, help="Open upload_dir command documentation page.")
def upload_dir(directory, glob_pattern, include_hidden, optional_parameter, optional_parameter_parsed, transformation,
               folder, folder_mode, preset, concurrent_workers, exclude_dir_name, doc):
    items, skipped = {}, {}

    if doc:
        return launch("https://cloudinary.com/documentation/cloudinary_cli#upload_dir")

    dir_to_upload = Path(path_join(getcwd(), directory))
    if not dir_to_upload.exists():
        logger.error(f"Directory: {dir_to_upload} does not exist")
        return False

    folder_mode = folder_mode or get_folder_mode()

    if exclude_dir_name:
        contents_str = "contents of"
        parent = dir_to_upload
    else:
        contents_str = ""
        parent = dirname(dir_to_upload)

    logger.info(f"Uploading {contents_str} directory '{dir_to_upload}' ({folder_mode} folder mode)")

    defaults = get_default_upload_options(folder_mode)

    upload_dir_options = {
        "raw_transformation": transformation,
        "upload_preset": preset
    }

    options = {
        **defaults,
        **upload_dir_options,
        **group_params(optional_parameter, ((k, parse_option_value(v)) for k, v in optional_parameter_parsed)),
    }

    uploads = []

    for file_path in dir_to_upload.glob(glob_pattern):
        if file_path.is_file():
            if not include_hidden and is_hidden_path(file_path):
                continue

            folder_options = get_destination_folder_options(str(file_path), folder, folder_mode, parent)
            uploads.append((file_path, {**options, **folder_options}, items, skipped))

    run_tasks_concurrently(upload_file, uploads, concurrent_workers)

    logger.info(style("{} resources uploaded".format(len(items)), fg="green"))

    if skipped:
        logger.warning("{} items skipped".format(len(skipped)))
        return False

    return True
