import logging
from collections import Counter
from itertools import groupby
from os import path, remove

from click import command, argument, option, style, UsageError
from cloudinary import api

from cloudinary_cli.utils.api_utils import query_cld_folder, upload_file, download_file
from cloudinary_cli.utils.file_utils import walk_dir, delete_empty_dirs, get_destination_folder, \
    normalize_file_extension, posix_rel_path
from cloudinary_cli.utils.json_utils import print_json, read_json_from_file, write_json_to_file
from cloudinary_cli.utils.utils import logger, run_tasks_concurrently, get_user_action, invert_dict, chunker

_DEFAULT_DELETION_BATCH_SIZE = 30
_DEFAULT_CONCURRENT_WORKERS = 30

_SYNC_META_FILE = '.cld-sync'


@command("sync",
         short_help="Synchronize between a local directory and a Cloudinary folder.",
         help="Synchronize between a local directory and a Cloudinary folder, maintaining the folder structure.")
@argument("local_folder")
@argument("cloudinary_folder")
@option("--push", help="Push changes from your local folder to your Cloudinary folder.", is_flag=True)
@option("--pull", help="Pull changes from your Cloudinary folder to your local folder.", is_flag=True)
@option("-H", "--include-hidden", is_flag=True, help="Include hidden files in sync.")
@option("-w", "--concurrent_workers", type=int, default=_DEFAULT_CONCURRENT_WORKERS,
        help="Specify the number of concurrent network threads.")
@option("-F", "--force", is_flag=True, help="Skip confirmation when deleting files.")
@option("-K", "--keep-unique", is_flag=True, help="Keep unique files in the destination folder.")
@option("-D", "--deletion-batch-size", type=int, default=_DEFAULT_DELETION_BATCH_SIZE,
        help="Specify the batch size for deleting remote assets.")
def sync(local_folder, cloudinary_folder, push, pull, include_hidden, concurrent_workers, force, keep_unique,
         deletion_batch_size):
    if push == pull:
        raise UsageError("Please use either the '--push' OR '--pull' options")

    sync_dir = SyncDir(local_folder, cloudinary_folder, include_hidden, concurrent_workers, force, keep_unique,
                       deletion_batch_size)

    result = True
    if push:
        result = sync_dir.push()
    elif pull:
        result = sync_dir.pull()

    logger.info("Done!")

    return result


class SyncDir:
    def __init__(self, local_dir, remote_dir, include_hidden, concurrent_workers, force, keep_deleted,
                 deletion_batch_size):
        self.local_dir = local_dir
        self.remote_dir = remote_dir.strip('/')
        self.user_friendly_remote_dir = self.remote_dir if self.remote_dir else '/'
        self.include_hidden = include_hidden
        self.concurrent_workers = concurrent_workers
        self.force = force
        self.keep_unique = keep_deleted
        self.deletion_batch_size = deletion_batch_size

        self.sync_meta_file = path.join(self.local_dir, _SYNC_META_FILE)

        self.verbose = logger.getEffectiveLevel() < logging.INFO

        self.local_files = walk_dir(path.abspath(self.local_dir), include_hidden)
        logger.info(f"Found {len(self.local_files)} items in local folder '{local_dir}'")

        self.remote_files = query_cld_folder(self.remote_dir)
        logger.info(f"Found {len(self.remote_files)} items in Cloudinary folder '{self.user_friendly_remote_dir}'")

        local_file_names = self.local_files.keys()
        remote_file_names = self.remote_files.keys()
        """
        Cloudinary is a very permissive service. When uploading files that contain invalid characters, 
        unicode characters, etc, Cloudinary does the best effort to store those files. 
        
        Usually Cloudinary sanitizes those file names and strips invalid characters. Although it is a good best effort 
        for a general use case, when syncing local folder with Cloudinary, it is not the best option, since directories 
        will be always out-of-sync.
         
        To overcome this limitation, cloudinary-cli keeps .cld-sync hidden file in the sync directory that contains a 
        mapping of the diverse file names. This file keeps tracking of the files and allows syncing in both directions.
        """
        diverse_file_names = read_json_from_file(self.sync_meta_file, does_not_exist_ok=True)
        self.diverse_file_names = dict(
            (normalize_file_extension(k), normalize_file_extension(v)) for k, v in diverse_file_names.items())
        inverted_diverse_file_names = invert_dict(self.diverse_file_names)

        cloudinarized_local_file_names = [self.diverse_file_names.get(f, f) for f in local_file_names]
        self.recovered_remote_files = {inverted_diverse_file_names.get(f, f): dt for f, dt in self.remote_files.items()}

        self.unique_remote_file_names = remote_file_names - cloudinarized_local_file_names
        self.unique_local_file_names = local_file_names - self.recovered_remote_files.keys()

        common_file_names = local_file_names - self.unique_local_file_names

        self.out_of_sync_local_file_names = self._get_out_of_sync_file_names(common_file_names)
        self.out_of_sync_remote_file_names = set(self.diverse_file_names.get(f, f) for f in
                                                 self.out_of_sync_local_file_names)

        self.synced_files_count = len(common_file_names) - len(self.out_of_sync_local_file_names)

        if self.synced_files_count:
            logger.info(f"Skipping {self.synced_files_count} items")

    def push(self):
        """
        Pushes changes from the local folder to the Cloudinary folder.
        """
        if not self._handle_unique_remote_files():
            logger.info("Aborting...")
            return False

        files_to_push = self.unique_local_file_names | self.out_of_sync_local_file_names
        if not files_to_push:
            return True

        logger.info(f"Uploading {len(files_to_push)} items to Cloudinary folder '{self.user_friendly_remote_dir}'")

        options = {
            'use_filename': True,
            'unique_filename': False,
            'invalidate': True,
            'resource_type': 'auto'
        }
        upload_results = {}
        upload_errors = {}
        uploads = []
        for file in files_to_push:
            folder = get_destination_folder(self.remote_dir, file)

            uploads.append(
                (self.local_files[file]['path'], {**options, 'folder': folder}, upload_results, upload_errors))

        try:
            run_tasks_concurrently(upload_file, uploads, self.concurrent_workers)
        finally:
            self._print_sync_status(upload_results, upload_errors)
            self._save_sync_meta_file(upload_results)

        if upload_errors:
            raise Exception("Sync did not finish successfully")

    def pull(self):
        """
        Pulls changes from the Cloudinary folder to the local folder.
        """
        download_results = {}
        download_errors = {}
        if not self._handle_unique_local_files():
            return False

        files_to_pull = self.unique_remote_file_names | self.out_of_sync_remote_file_names

        if not files_to_pull:
            return True

        logger.info(f"Downloading {len(files_to_pull)} files from Cloudinary")
        downloads = []
        for file in files_to_pull:
            remote_file = self.remote_files[file]
            local_path = path.abspath(path.join(self.local_dir, file))

            downloads.append((remote_file, local_path, download_results, download_errors))

        try:
            run_tasks_concurrently(download_file, downloads, self.concurrent_workers)
        finally:
            self._print_sync_status(download_results, download_errors)

        if download_errors:
            raise Exception("Sync did not finish successfully")

    def _print_sync_status(self, success, errors):
        logger.info("==Sync Status==")
        logger.info("===============")
        logger.info(f"In Sync| {self.synced_files_count}")
        logger.info(f"Synced | {len(success)}")
        logger.info(f"Failed | {len(errors)}")
        logger.info("===============")

    def _save_sync_meta_file(self, upload_results):
        diverse_filenames = {}
        for local_path, remote_path in upload_results.items():
            local = normalize_file_extension(posix_rel_path(local_path, self.local_dir))
            remote = normalize_file_extension(posix_rel_path(remote_path, self.remote_dir))
            if local != remote:
                diverse_filenames[local] = remote

        # filter out outdated meta file entries
        current_diverse_files = {k: v for k, v in self.diverse_file_names.items() if k in self.local_files.keys()}

        if diverse_filenames or current_diverse_files != self.diverse_file_names:
            current_diverse_files.update(diverse_filenames)
            try:
                logger.debug(f"Updating '{self.sync_meta_file}' file")
                write_json_to_file(current_diverse_files, self.sync_meta_file)
                logger.debug(f"Updated '{self.sync_meta_file}' file")
            except Exception as e:
                # Meta file is not critical for the sync itself, in case we cannot write it, we just log a warning
                logger.warning(f"Failed updating '{self.sync_meta_file}' file: {e}")

    def _handle_unique_remote_files(self):
        """
        Handles remote files (on Cloudinary servers) that do not exist in the local folder.
        User can decide to keep them or to delete. Optionally user can abort the operation.

        :return: True if successful, otherwise False
        """
        handled = self._handle_files_deletion(len(self.unique_remote_file_names), "remote")
        if handled is not None:
            return handled

        logger.info(f"Deleting {len(self.unique_remote_file_names)} resources "
                    f"from Cloudinary folder '{self.user_friendly_remote_dir}'")
        files_to_delete_from_cloudinary = list(map(lambda x: self.remote_files[x], self.unique_remote_file_names))

        # We group files into batches by resource_type and type to reduce the number of API calls.
        batches = groupby(files_to_delete_from_cloudinary, lambda file: (file["resource_type"], file["type"]))
        for attrs, batch_iter in batches:
            batch = [file["public_id"] for file in batch_iter]
            logger.info("Deleting {} resources with resource_type '{}' and type '{}'".format(len(batch), *attrs))

            # Each batch is further chunked by a deletion batch size that can be specified by the user.
            for deletion_batch in chunker(batch, self.deletion_batch_size):
                res = api.delete_resources(deletion_batch, invalidate=True, resource_type=attrs[0], type=attrs[1])
                num_deleted = Counter(res['deleted'].values())["deleted"]
                if self.verbose:
                    print_json(res)
                if num_deleted != len(deletion_batch):
                    # This should not happen in reality, unless some terrible race condition happens with the folder.
                    failed = [f"{file}: {reason}" for file, reason in res['deleted'].items() if reason != "deleted"]
                    logger.error("Failed deletes:\n{}".format("\n".join(failed)))
                else:
                    logger.info(style(f"Deleted {num_deleted} resources", fg="green"))

        return True

    def _get_out_of_sync_file_names(self, common_file_names):
        logger.debug("\nCalculating differences...\n")
        out_of_sync_file_names = set()
        for f in common_file_names:
            local_etag = self.local_files[f]['etag']
            remote_etag = self.recovered_remote_files[f]['etag']
            if local_etag != remote_etag:
                logger.warning(f"'{f}' is out of sync" +
                               (f" with '{self.diverse_file_names[f]}'" if f in self.diverse_file_names else ""))
                logger.debug(f"Local etag: {local_etag}. Remote etag: {remote_etag}")
                out_of_sync_file_names.add(f)
                continue
            logger.debug(f"'{f}' is in sync" +
                         (f" with '{self.diverse_file_names[f]}'" if f in self.diverse_file_names else ""))

        return out_of_sync_file_names

    def _handle_unique_local_files(self):
        """
        Handles local files that do not exist on the Cloudinary server.
        User can decide to keep them or to delete. Optionally user can abort the operation.

        :return: True if successful, otherwise False
        """
        handled = self._handle_files_deletion(len(self.unique_local_file_names), "local")
        if handled is not None:
            return handled

        logger.info(f"Deleting {len(self.unique_local_file_names)} local files...")
        for file in self.unique_local_file_names:
            full_path = path.abspath(self.local_files[file]['path'])
            remove(full_path)
            logger.info(f"Deleted '{full_path}'")

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
