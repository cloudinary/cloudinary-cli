from functools import reduce
from itertools import product
from os import walk, sep, remove, rmdir, listdir, mkdir
from os.path import splitext, split, join as path_join, abspath, isdir
from threading import Thread, active_count
from time import sleep

from click import command, argument, option, style
from cloudinary import uploader as _uploader, api
from cloudinary.search import Search
from cloudinary.utils import cloudinary_url as cld_url
from requests import get

from cloudinary_cli.utils import log_json, etag, logger


@command("sync",
         short_help="Synchronize between a local directory and a Cloudinary folder.",
         help="Synchronize between a local directory and a Cloudinary folder, maintaining the folder structure.")
@argument("local_folder")
@argument("cloudinary_folder")
@option("--push", help="Push changes from your local folder to your Cloudinary folder.", is_flag=True)
@option("--pull", help="Pull changes from your Cloudinary folder to your local folder.", is_flag=True)
@option("-v", "--verbose", is_flag=True, help="Output status details after each upload, download or deletion.")
def sync(local_folder, cloudinary_folder, push, pull, verbose):
    if push == pull:
        raise Exception("Please use either the '--push' OR '--pull' options")

    def walk_dir(folder):
        all_files = {}
        for root, _, files in walk(folder):
            for _file in files:
                all_files[splitext(path_join(root, _file)[len(folder) + 1:])[0]] = {
                    "etag": etag(path_join(root, _file)), "path": path_join(root, _file)}
        return all_files

    def query_cld_folder(folder):
        next_cursor = None
        items = {}
        while True:
            res = Search().expression("folder:{}/*".format(folder)).next_cursor(next_cursor).with_field(
                "image_analysis").max_results(500).execute()
            for item in res['resources']:
                items[item['public_id'][len(folder) + 1:]] = {"etag": item['etag'] if 'etag' in item.keys() else '0',
                                                              "resource_type": item['resource_type'],
                                                              "public_id": item['public_id'], "type": item['type'],
                                                              "format": item['format']}
            if 'next_cursor' not in res.keys():
                break
            else:
                next_cursor = res['next_cursor']
        return items

    files = walk_dir(abspath(local_folder))
    logger.info("Found {} items in local folder '{}'".format(len(files.keys()), local_folder))
    cld_files = query_cld_folder(cloudinary_folder)
    logger.info("Found {} items in Cloudinary folder '{}'".format(len(cld_files.keys()), cloudinary_folder))
    files_ = set(files.keys())
    cld_files_ = set(cld_files.keys())

    files_in_cloudinary_nin_local = cld_files_ - files_
    files_in_local_nin_cloudinary = files_ - cld_files_
    skipping = 0

    if push:

        files_to_delete_from_cloudinary = list(cld_files_ - files_)
        files_to_push = files_ - cld_files_
        files_to_check = files_ - files_to_push
        logger.info("\nCalculating differences...\n")
        for f in files_to_check:
            if files[f]['etag'] == cld_files[f]['etag']:
                if verbose:
                    logger.warning("{} already exists in Cloudinary".format(f))
                skipping += 1
            else:
                files_to_push.add(f)
        logger.info("Skipping upload for {} items".format(skipping))
        if len(files_to_delete_from_cloudinary) > 0:
            logger.info("Deleting {} resources from Cloudinary folder '{}'".format(len(files_to_delete_from_cloudinary),
                                                                                   cloudinary_folder))
            files_to_delete_from_cloudinary = list(map(lambda x: cld_files[x], files_to_delete_from_cloudinary))

            for i in product({"upload", "private", "authenticated"}, {"image", "video", "raw"}):
                batch = list(map(lambda x: x['public_id'],
                                 filter(lambda x: x["type"] == i[0] and x["resource_type"] == i[1],
                                        files_to_delete_from_cloudinary)))
                if len(batch) > 0:
                    logger.info("Deleting {} resources with type '{}' and resource_type '{}'".format(len(batch), *i))
                    counter = 0
                    while counter * 100 < len(batch) and len(batch) > 0:
                        counter += 1
                        res = api.delete_resources(batch[(counter - 1) * 100:counter * 100], invalidate=True,
                                                   resource_type=i[1], type=i[0])
                        num_deleted = reduce(lambda x, y: x + 1 if y == "deleted" else x, res['deleted'].values(), 0)
                        if verbose:
                            log_json(res)
                        if num_deleted != len(batch):
                            logger.error("Failed deletes:\n{}".format("\n".join(list(
                                map(lambda x: x[0], filter(lambda x: x[1] != 'deleted', res['deleted'].items()))))))
                        else:
                            logger.info(style("Deleted {} resources".format(num_deleted), fg="green"))

        to_upload = list(filter(lambda x: split(x)[1][0] != ".", files_to_push))
        logger.info("Uploading {} items to Cloudinary folder '{}'".format(len(to_upload), cloudinary_folder))

        threads = []

        def threaded_upload(options, path, verbose):
            res = _uploader.upload(path, **options)
            if verbose:
                logger.info(style("Uploaded '{}'".format(res['public_id']), fg="green"))

        for i in to_upload:
            modif_folder = path_join(cloudinary_folder, sep.join(i.split(sep)[:-1]))
            options = {'use_filename': True, 'unique_filename': False, 'folder': modif_folder, 'invalidate': True,
                       'resource_type': 'auto'}
            threads.append(Thread(target=threaded_upload, args=(options, files[i]['path'], verbose)))

        for t in threads:
            while active_count() >= 30:
                # prevent concurrency overload
                sleep(1)
            t.start()
            sleep(1 / 10)

        [t.join() for t in threads]

        logger.info("Done!")

    else:
        files_to_delete_local = list(files_in_local_nin_cloudinary)
        files_to_pull = files_in_cloudinary_nin_local
        files_to_check = cld_files_ - files_to_pull

        logger.info("\nCalculating differences...\n")
        for f in files_to_check:
            if files[f]['etag'] == cld_files[f]['etag']:
                if verbose:
                    logger.info("{} already exists locally".format(f))
                skipping += 1
            else:
                files_to_pull.add(f)
        logger.warn("Skipping download for {} items".format(skipping))

        def delete_empty_folders(root, verbose, remove_root=False):
            if not isdir(root):
                return

            files = listdir(root)
            if len(files):
                for f in files:
                    fullpath = path_join(root, f)
                    if isdir(fullpath):
                        delete_empty_folders(fullpath, verbose, True)

            files = listdir(root)
            if len(files) == 0 and remove_root:
                if verbose:
                    logger.info("Removing empty folder '{}'".format(root))
                rmdir(root)

        def create_required_directories(root, verbose):
            if isdir(root):
                return
            else:
                create_required_directories(sep.join(root.split(sep)[:-1]), verbose)
                if verbose:
                    logger.info("Creating directory '{}'".format(root))
                mkdir(root)

        logger.info("Deleting {} local files...".format(len(files_to_delete_local)))
        for i in files_to_delete_local:
            remove(abspath(files[i]['path']))
            if verbose:
                logger.info("Deleted '{}'".format(abspath(files[i]['path'])))

        logger.info("Deleting empty folders...")

        delete_empty_folders(local_folder, verbose)

        logger.info("Downloading {} files from Cloudinary".format(len(files_to_pull)))

        threads = []

        def threaded_pull(local_path, verbose, cld_files, i):
            with open(local_path, "wb") as f:
                to_download = cld_files[i]
                r = get(cld_url(to_download['public_id'], resource_type=to_download['resource_type'],
                                type=to_download['type'])[0])
                f.write(r.content)
                f.close()
            if verbose:
                logger.info(style("Downloaded '{}' to '{}'".format(i, local_path), fg="green"))

        for i in files_to_pull:
            local_path = abspath(path_join(local_folder,
                                           i + "." + cld_files[i]['format']
                                           if cld_files[i]['resource_type'] != 'raw' else i))
            create_required_directories(split(local_path)[0], verbose)

            threads.append(Thread(target=threaded_pull, args=(local_path, verbose, cld_files, i)))

        for t in threads:
            while active_count() >= 30:
                # prevent concurrency overload
                sleep(1)
            t.start()
            sleep(1 / 10)

        [t.join() for t in threads]

        logger.info("Done!")
