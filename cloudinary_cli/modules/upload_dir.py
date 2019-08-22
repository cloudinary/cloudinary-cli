from click import command, argument, option
from cloudinary import uploader as _uploader
from os import getcwd, walk, sep, remove, rmdir, listdir, mkdir
from os.path import dirname, splitext, split, join as path_join, abspath, isdir
from threading import Thread, active_count
from time import sleep
from ..utils import parse_option_value, log, F_OK, F_WARN, F_FAIL, load_template

@command("upload_dir",
         help="""Upload a directory of assets and persist the directory structure""")
@argument("directory", default=".")
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2, help="Pass optional parameters as interpreted strings")
@option("-t", "--transformation", help="Transformation to apply on all uploads")
@option("-f", "--folder", default="", help="Specify the folder you would like to upload resources to in Cloudinary")
@option("-p", "--preset", help="Upload preset to use")
@option("-v", "--verbose", is_flag=True, help="Logs information after each upload")
def upload_dir(directory, optional_parameter, optional_parameter_parsed, transformation, folder, preset, verbose):
    items, skipped = [], []
    dir_to_upload = abspath(path_join(getcwd(), directory))
    print("Uploading directory '{}'".format(dir_to_upload))
    parent = dirname(dir_to_upload)
    options = {
        **{k:v for k,v in optional_parameter},
        **{k:parse_option_value(v) for k,v in optional_parameter_parsed},
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
            print(F_OK("Successfully uploaded {} as {}".format(file_path, _r['public_id'])))
            if v:
                log(_r)
            items.append(_r['public_id'])
        except Exception as e:
            print(F_FAIL("Failed uploading {}".format(file_path)))
            print(e)
            skipped.append(file_path)
            pass

    for root, _, files in walk(dir_to_upload):
        for fi in files:
            file_path = abspath(path_join(dir_to_upload, root, fi))
            mod_folder = path_join(folder, dirname(file_path[len(parent) + 1:]))
            if split(file_path)[1][0] == ".":
                continue
            options = {**options, "folder": mod_folder}
            threads.append(Thread(target=upload_multithreaded, args=(file_path, items, skipped, verbose), kwargs=options))

    for t in threads:
        while active_count() >= 30:
            # prevent concurrency overload
            sleep(1)
        t.start()
        sleep(1/10)

    for t in threads: t.join()

    print(F_OK("\n{} resources uploaded:".format(len(items))))
    print(F_OK('\n'.join(items)))
    if len(skipped):
        print(F_FAIL("\n{} items skipped:".format(len(skipped))))
        print(F_FAIL('\n'.join(skipped)))