import logging
from functools import reduce
from itertools import product
from os import remove
from os.path import join as path_join, abspath

from click import command, argument, option, style
from cloudinary import api

from cloudinary_cli.utils.api_utils import query_cld_folder, upload_file, download_file
from cloudinary_cli.utils.file_utils import walk_dir, delete_empty_dirs, get_destination_folder
from cloudinary_cli.utils.json_utils import print_json
from cloudinary_cli.utils.utils import logger, run_tasks_concurrently, get_user_action

DELETE_ASSETS_BATCH_SIZE = 100


@command("sync",
         short_help="Synchronize between a local directory and a Cloudinary folder.",
         help="Synchronize between a local directory and a Cloudinary folder, maintaining the folder structure.")
@argument("local_folder")
@argument("cloudinary_folder")
@option("--push", help="Push changes from your local folder to your Cloudinary folder.", is_flag=True)
@option("--pull", help="Pull changes from your Cloudinary folder to your local folder.", is_flag=True)
@option("-w", "--concurrent_workers", type=int, default=30, help="Specify number of concurrent network threads.")
@option("-F", "--force", is_flag=True, help="Skip confirmation when deleting files.")
@option("-K", "--keep-unique", is_flag=True, help="Keep unique files in the destination folder.")
def sync(local_folder, cloudinary_folder, push, pull, concurrent_workers, force, keep_unique):
    if push == pull:
        raise Exception("Please use either the '--push' OR '--pull' options")

    sync_dir = SyncDir(local_folder, cloudinary_folder, concurrent_workers, force, keep_unique)

    if push:
        sync_dir.push()
    elif pull:
        sync_dir.pull()

    logger.info("Done!")


class SyncDir:
    def __init__(self, local_dir, remote_dir, concurrent_workers, force, keep_deleted):
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        self.concurrent_workers = concurrent_workers
        self.force = force
        self.keep_unique = keep_deleted

        self.verbose = logger.getEffectiveLevel() < logging.INFO

        self.local_files = walk_dir(abspath(self.local_dir))
        logger.info(f"Found {len(self.local_files)} items in local folder '{local_dir}'")

        self.remote_files = query_cld_folder(self.remote_dir)
        logger.info(f"Found {len(self.remote_files)} items in Cloudinary folder '{self.remote_dir}'")

        local_file_names = self.local_files.keys()
        remote_file_names = self.remote_files.keys()

        self.unique_remote_file_names = remote_file_names - local_file_names
        self.unique_local_file_names = local_file_names - remote_file_names
        common_file_names = local_file_names - self.unique_local_file_names

        self.out_of_sync_file_names = self._get_out_of_sync_file_names(common_file_names)

        skipping = len(common_file_names) - len(self.out_of_sync_file_names)

        if skipping:
            logger.info(f"Skipping {skipping} items")

    def _get_out_of_sync_file_names(self, common_file_names):
        logger.debug("\nCalculating differences...\n")
        out_of_sync_file_names = set()
        for f in common_file_names:
            if self.local_files[f]['etag'] != self.remote_files[f]['etag']:
                logger.warning(f"{f} is out of sync")
                logger.debug(f"Local etag: {self.local_files[f]['etag']}. Remote etag: {self.remote_files[f]['etag']}")
                out_of_sync_file_names.add(f)
                continue
            logger.debug(f"{f} is in sync")

        return out_of_sync_file_names

    def push(self):
        if not self._handle_unique_remote_files():
            logger.info("Aborting...")
            return False

        files_to_push = self.unique_local_file_names | self.out_of_sync_file_names
        if not files_to_push:
            return True

        logger.info(f"Uploading {len(files_to_push)} items to Cloudinary folder '{self.remote_dir}'")

        options = {
            'use_filename': True,
            'unique_filename': False,
            'invalidate': True,
            'resource_type': 'auto'
        }
        uploads = []
        for file in files_to_push:
            folder = get_destination_folder(self.remote_dir, file)

            uploads.append((self.local_files[file]['path'], {**options, 'folder': folder}))

        run_tasks_concurrently(upload_file, uploads, self.concurrent_workers)

    def _handle_unique_remote_files(self):
        handled = self._handle_files_deletion(len(self.unique_remote_file_names), "remote")
        if handled is not None:
            return handled

        logger.info(f"Deleting {len(self.unique_remote_file_names)} resources "
                    f"from Cloudinary folder '{self.remote_dir}'")
        files_to_delete_from_cloudinary = list(map(lambda x: self.remote_files[x], self.unique_remote_file_names))

        for i in product({"upload", "private", "authenticated"}, {"image", "video", "raw"}):
            batch = list(map(lambda x: x['public_id'],
                             filter(lambda x: x["type"] == i[0] and x["resource_type"] == i[1],
                                    files_to_delete_from_cloudinary)))
            if not len(batch):
                continue

            logger.info("Deleting {} resources with type '{}' and resource_type '{}'".format(len(batch), *i))
            counter = 0
            while counter * DELETE_ASSETS_BATCH_SIZE < len(batch) and len(batch) > 0:
                counter += 1
                res = api.delete_resources(
                    batch[(counter - 1) * DELETE_ASSETS_BATCH_SIZE:counter * DELETE_ASSETS_BATCH_SIZE], invalidate=True,
                    resource_type=i[1], type=i[0])
                num_deleted = reduce(lambda x, y: x + 1 if y == "deleted" else x, res['deleted'].values(), 0)
                if self.verbose:
                    print_json(res)
                if num_deleted != len(batch):
                    logger.error("Failed deletes:\n{}".format("\n".join(list(
                        map(lambda x: x[0], filter(lambda x: x[1] != 'deleted', res['deleted'].items()))))))
                else:
                    logger.info(style(f"Deleted {num_deleted} resources", fg="green"))

        return True

    def pull(self):
        if not self._handle_unique_local_files():
            return False

        files_to_pull = self.unique_remote_file_names | self.out_of_sync_file_names

        if not files_to_pull:
            return True

        logger.info(f"Downloading {len(files_to_pull)} files from Cloudinary")
        downloads = []
        for file in files_to_pull:
            remote_file = self.remote_files[file]
            local_path = abspath(path_join(self.local_dir, file))

            downloads.append((remote_file, local_path))

        run_tasks_concurrently(download_file, downloads, self.concurrent_workers)

    def _handle_unique_local_files(self):
        handled = self._handle_files_deletion(len(self.unique_local_file_names), "local")
        if handled is not None:
            return handled

        logger.info(f"Deleting {len(self.unique_local_file_names)} local files...")
        for file in self.unique_local_file_names:
            path = abspath(self.local_files[file]['path'])
            remove(path)
            logger.info(f"Deleted '{path}'")

        logger.info("Deleting empty folders...")
        delete_empty_dirs(self.local_dir)

        return True

    def _handle_files_deletion(self, num_files, location):
        if not num_files:
            logger.debug("No files found for deletion.")
            return True

        decision = self._handle_files_deletion_decision(num_files, location)

        if decision is True:
            logger.info(f"Keeping {num_files} {location} files...")
            return True
        elif decision is False:
            logger.info("Aborting...")
            return False

        return decision

    def _handle_files_deletion_decision(self, num_files, location):
        if self.keep_unique:
            return True

        if self.force:
            return None

        decision = get_user_action(
            f"Running this command will delete {num_files} {location} files.\n"
            f"To keep the files and continue partial sync, please choose k.\n"
            f"Continue? (y/k/N)",
            {
                "y": None,
                "k": True,
                "default": False
            }
        )

        return decision
