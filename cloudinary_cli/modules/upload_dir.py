from os import getcwd, walk
from os.path import dirname, split, join as path_join, abspath
from threading import Thread, active_count
from time import sleep

from click import command, argument, option, echo, style
from cloudinary import uploader as _uploader

from cloudinary_cli.utils import parse_option_value, log_json, logger


@command("upload_dir",
         help="""Upload a folder of assets, maintaining the folder structure.""")
@argument("directory", default=".")
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed",
        multiple=True,
        nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("-t", "--transformation", help="The transformation to apply on all uploads.")
@option("-f", "--folder", default="",
        help="The Cloudinary folder where you want to upload the assets. You can specify a whole path, for example folder1/folder2/folder3. Any folders that do not exist are automatically created.")
@option("-p", "--preset", help="The upload preset to use.")
@option("-v", "--verbose", is_flag=True, help="Output information for each uploaded file.")
def upload_dir(directory, optional_parameter, optional_parameter_parsed, transformation, folder, preset, verbose):
    items, skipped = [], []
    dir_to_upload = abspath(path_join(getcwd(), directory))
    echo("Uploading directory '{}'".format(dir_to_upload))
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

    threads = []

    def upload_multithreaded(file_path, items, skipped, v, **kwargs):
        try:
            _r = _uploader.upload(file_path, **kwargs)
            echo("Successfully uploaded {} as {}".format(file_path, _r['public_id']))
            if v:
                log_json(_r)
            items.append(_r['public_id'])
        except Exception:
            logger.error("Failed uploading {}".format(file_path))
            skipped.append(file_path)
            pass

    for root, _, files in walk(dir_to_upload):
        for fi in files:
            file_path = abspath(path_join(dir_to_upload, root, fi))
            mod_folder = path_join(folder, dirname(file_path[len(parent) + 1:]))
            if split(file_path)[1][0] == ".":
                continue
            options = {**options, "folder": mod_folder}
            threads.append(Thread(target=upload_multithreaded,
                                  args=(file_path, items, skipped, verbose),
                                  kwargs=options))

    for t in threads:
        while active_count() >= 30:
            # prevent concurrency overload
            sleep(1)
        t.start()
        sleep(1 / 10)

    for t in threads:
        t.join()
    logger.info(style("{} resources uploaded".format(len(items)), fg="green"))
    if len(skipped):
        logger.warn("{} items skipped".format(len(skipped)))
