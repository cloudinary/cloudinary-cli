import logging
import os.path
import re
from collections import Counter
from itertools import groupby
from os import path, remove

from click import command, argument, option, style, UsageError, Choice
from cloudinary import api

from cloudinary_cli.utils.api_utils import query_cld_folder, upload_file, download_file, get_folder_mode, \
    get_default_upload_options, get_destination_folder_options, cld_folder_exists
from cloudinary_cli.utils.file_utils import (walk_dir, delete_empty_dirs, normalize_file_extension, posix_rel_path,
                                             populate_duplicate_name)
from cloudinary_cli.utils.json_utils import print_json, read_json_from_file, write_json_to_file
from cloudinary_cli.utils.utils import logger, run_tasks_concurrently, get_user_action, invert_dict, chunker, \
    group_params, parse_option_value, duplicate_values

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
@option("-fm", "--folder-mode", type=Choice(['fixed', 'dynamic'], case_sensitive=False),
        help="Specify folder mode explicitly. By default uses cloud mode configured in your cloud.", hidden=True)
@option("-st", "--status", type=Choice(['all', 'active', 'pending'], case_sensitive=False),
        help="Specify asset status. Server default: active.", default=None)
@option("-o", "--optional_parameter", multiple=True, nargs=2, help="Pass optional parameters as raw strings.")
@option("-O", "--optional_parameter_parsed", multiple=True, nargs=2,
        help="Pass optional parameters as interpreted strings.")
@option("--dry-run", is_flag=True, help="Simulate the sync operation without making any changes.")
def sync(local_folder, cloudinary_folder, push, pull, include_hidden, concurrent_workers, force, keep_unique,
         deletion_batch_size, folder_mode, status, optional_parameter, optional_parameter_parsed, dry_run):
    if push == pull:
        raise UsageError("Please use either the '--push' OR '--pull' options")

    sync_dir = SyncDir(local_folder, cloudinary_folder, include_hidden, concurrent_workers, force, keep_unique,
                       deletion_batch_size, folder_mode, status, optional_parameter, optional_parameter_parsed, dry_run)
    result = True
    if push:
        result = sync_dir.push()
    elif pull:
        result = sync_dir.pull()

    if result:
        logger.info("Done!")

    return result


class SyncDir:
    def __init__(self, local_dir, remote_dir, include_hidden, concurrent_workers, force, keep_deleted,
                 deletion_batch_size, folder_mode, status, optional_parameter, optional_parameter_parsed, dry_run):
        self.local_dir = local_dir
        self.remote_dir = remote_dir.strip('/')
        self.user_friendly_remote_dir = self.remote_dir if self.remote_dir else '/'
        self.include_hidden = include_hidden
        self.concurrent_workers = concurrent_workers
        self.force = force
        self.keep_unique = keep_deleted
        self.deletion_batch_size = deletion_batch_size
        self.dry_run = dry_run

        self.folder_mode = folder_mode or get_folder_mode()

        self.optional_parameter = optional_parameter
        self.optional_parameter_parsed = optional_parameter_parsed

        self.sync_meta_file = path.join(self.local_dir, _SYNC_META_FILE)

        self.verbose = logger.getEffectiveLevel() < logging.INFO

        self.local_files = {}
        self.local_folder_exists = os.path.isdir(path.abspath(self.local_dir))
        if not self.local_folder_exists:
            logger.info(f"Local folder '{self.local_dir}' does not exist.")
        else:
            self.local_files = walk_dir(path.abspath(self.local_dir), include_hidden)
            if len(self.local_files):
                logger.info(f"Found {len(self.local_files)} items in local folder '{self.local_dir}'")
            else:
                logger.info(f"Local folder '{self.local_dir}' is empty.")

        raw_remote_files = {}
        self.cld_folder_exists = cld_folder_exists(self.remote_dir)
        if not self.cld_folder_exists:
            logger.info(f"Cloudinary folder '{self.user_friendly_remote_dir}' does not exist "
                           f"({self.folder_mode} folder mode).")
        else:
            raw_remote_files = query_cld_folder(self.remote_dir, self.folder_mode, status)
            if len(raw_remote_files):
                logger.info(
                    f"Found {len(raw_remote_files)} items in Cloudinary folder '{self.user_friendly_remote_dir}' "
                    f"({self.folder_mode} folder mode).")
            else:
                logger.info(f"Cloudinary folder '{self.user_friendly_remote_dir}' is empty. "
                            f"({self.folder_mode} folder mode)")

        self.remote_files = self._normalize_remote_file_names(raw_remote_files, self.local_files)
        self.remote_duplicate_names = duplicate_values(self.remote_files, "normalized_path", "asset_id")
        self._print_duplicate_file_names()

        local_file_names = self.local_files.keys()
        remote_file_names = self.remote_files.keys()
        """
        Cloudinary is a very permissive service. When uploading files that contain invalid characters,
        unicode characters, etc, Cloudinary does the best effort to store those files.

        Usually Cloudinary sanitizes those file names and strips invalid characters. Although it is a good best effort
        for a general use case, when syncing local folder with Cloudinary, it is not the best option, since directories
        will be always out-of-sync.

        In addition in dynamic folder mode Cloudinary allows having identical display names for differrent files.

        To overcome this limitation, cloudinary-cli keeps .cld-sync hidden file in the sync directory that contains a
        mapping of the diverse file names. This file keeps tracking of the files and allows syncing in both directions.
        """

        # handle fixed folder mode public_id differences
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

        if not self.local_folder_exists:
            logger.error(f"Cannot push a non-existent local folder '{self.local_dir}'. Aborting...")
            return False

        if not self._handle_unique_remote_files():
            logger.info("Aborting...")
            return False

        files_to_push = self.unique_local_file_names | self.out_of_sync_local_file_names
        if not files_to_push:
            return True

        if self.dry_run:
            logger.info("Dry run mode enabled. The following files would be uploaded:")
            for file in files_to_push:
                logger.info(f"{file}")
            return True

        logger.info(f"Uploading {len(files_to_push)} items to Cloudinary folder '{self.user_friendly_remote_dir}'")

        options = {
            **get_default_upload_options(self.folder_mode),
            **group_params(
                self.optional_parameter,
                ((k, parse_option_value(v)) for k, v in self.optional_parameter_parsed))
        }

        upload_results = {}
        upload_errors = {}
        uploads = []
        for file in files_to_push:
            folder_options = get_destination_folder_options(file, self.remote_dir, self.folder_mode)

            uploads.append(
                (self.local_files[file]['path'], {**options, **folder_options}, upload_results, upload_errors))

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

        if not self.cld_folder_exists:
            logger.error(f"Cannot pull from a non-existent Cloudinary folder '{self.user_friendly_remote_dir}' "
                         f"({self.folder_mode} folder mode). Aborting...")
            return False

        download_results = {}
        download_errors = {}
        if not self._handle_unique_local_files():
            return False

        files_to_pull = self.unique_remote_file_names | self.out_of_sync_remote_file_names

        if not files_to_pull:
            return True

        logger.info(f"Preparing to download {len(files_to_pull)} items from Cloudinary folder ")

        if self.dry_run:
            logger.info("Dry run mode enabled. The following files would be downloaded:")
            for file in files_to_pull:
                logger.info(f"{file}")
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

    def _normalize_remote_file_names(self, remote_files, local_files):
        """
        When multiple remote files have duplicate display name, we save them locally by appending index at the end
        of the base name, e.g. Image (1).jpg, Image (2).jpg, etc.

        For consistency, we sort files by `created_at` date.

        For partially synced files, when a remote file in the middle was deleted, we want to avoid resync
        of the remaining files.

        For example, if we had: Image (1), Image (2),..., Image(5), Image (10) on Cloudinary.
        If we delete "Image (2)" and resync - that would cause all files from Image (3) to Image (10) to be resynced.
        (Image (3) would become Image (2), ... Image (10) -> Image (9))

        Instead, since those indexes are arbitrary, we map local files to the remote files by etag (md5sum).
        Synced files will keep their indexes, out-of-sync files will be synced.

        :param remote_files: Remote files.
        :param local_files: Local files.
        :return:
        """
        duplicate_ids = duplicate_values(remote_files, "normalized_path")
        for duplicate_name, asset_ids in duplicate_ids.items():
            duplicate_dts = sorted([remote_files[asset_id] for asset_id in asset_ids], key=lambda f: f['created_at'])
            local_candidates = self._local_candidates(duplicate_name)
            remainng_duplicate_dts = []
            for duplicate_dt in duplicate_dts:
                matched_name = next((f for f in local_candidates.keys() if local_candidates[f] == duplicate_dt["etag"]),
                                    None)
                if matched_name is None:
                    remainng_duplicate_dts.append(duplicate_dt)
                    continue
                # found local synced file.
                remote_files[duplicate_dt["asset_id"]]["normalized_unique_path"] = matched_name
                local_candidates.pop(matched_name)

            unique_paths = {v["normalized_unique_path"] for v in remote_files.values()}
            curr_index = 0
            for dup in remainng_duplicate_dts:
                # here we check for collisions with other existing files.
                # remote file can have both "Image.jpg" and "Image (1).jpg", which are valid names, skip those.
                candidate_path = populate_duplicate_name(dup['normalized_path'], curr_index)
                while candidate_path in unique_paths:
                    curr_index += 1
                    candidate_path = populate_duplicate_name(dup['normalized_path'], curr_index)
                remote_files[dup["asset_id"]]["normalized_unique_path"] = candidate_path
                curr_index += 1

        return {dt["normalized_unique_path"]: dt for dt in remote_files.values()}

    def _local_candidates(self, candidate_path):
        filename, extension = path.splitext(candidate_path)
        r = re.compile(f"({candidate_path}|{filename} \\(\\d+\\){extension})")
        # sort local files by base name (without ext) for accurate results.
        return dict(sorted({f: self.local_files[f]["etag"] for f in filter(r.match, self.local_files.keys())}.items(),
                           key=lambda f: path.splitext(f[0])[0]))

    def _print_duplicate_file_names(self):
        if (len(self.remote_duplicate_names) > 0):
            logger.warning(f"Cloudinary folder '{self.user_friendly_remote_dir}' "
                           f"contains {len(self.remote_duplicate_names)} duplicate asset names")
            for normalized_path, asset_ids in self.remote_duplicate_names.items():
                logger.debug(f"Duplicate name: '{normalized_path}', asset ids: {', '.join(asset_ids)}")

    def _print_sync_status(self, success, errors):
        logger.info("==Sync Status==")
        logger.info("===============")
        logger.info(f"In Sync| {self.synced_files_count}")
        logger.info(f"Synced | {len(success)}")
        logger.info(f"Failed | {len(errors)}")
        logger.info("===============")

    def _save_sync_meta_file(self, upload_results):
        diverse_filenames = {}
        for local_path, remote_res in upload_results.items():
            remote_path = remote_res["display_path"] if self.folder_mode == "dynamic" else remote_res["path"]
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
                if self.dry_run:
                    logger.info(f"Dry run mode enabled. Would delete {len(deletion_batch)} resources:\n" +
                                                "\n".join(deletion_batch))
                    continue
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
                         (f" with '{self.diverse_file_names[f]}'" if f in self.diverse_file_names else "") +
                         (f". Public ID: {self.recovered_remote_files[f]['public_id']}"
                          if self.folder_mode == "dynamic" else "")
                         )

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
            if self.dry_run:
                logger.info(f"Dry run mode enabled. Would delete '{full_path}'")
                continue
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
