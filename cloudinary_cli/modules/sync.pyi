from typing import Dict, Any, List, Tuple, Optional

class SyncDir:
    def __init__(self, local_dir: str, remote_dir: str, include_hidden: bool, 
                 concurrent_workers: int, force: bool, keep_deleted: bool, 
                 deletion_batch_size: int, folder_mode: Optional[str], 
                 optional_parameter: Optional[List[Tuple[str, str]]], 
                 optional_parameter_parsed: Optional[List[Tuple[str, str]]]) -> None:
        self.local_dir: str
        self.remote_dir: str
        self.user_friendly_remote_dir: str
        self.include_hidden: bool
        self.concurrent_workers: int
        self.force: bool
        self.keep_unique: bool
        self.deletion_batch_size: int
        self.folder_mode: Optional[str]
        self.optional_parameter: Optional[List[Tuple[str, str]]]
        self.optional_parameter_parsed: Optional[List[Tuple[str, str]]]
        self.sync_meta_file: str
        self.verbose: bool
        self.local_files: Dict[str, Dict[str, Any]]
        self.local_folder_exists: bool
        self.remote_files: Dict[str, Dict[str, Any]]
        self.remote_duplicate_names: Dict[str, List[str]]
        self.diverse_file_names: Dict[str, str]
        self.recovered_remote_files: Dict[str, Dict[str, Any]]
        self.unique_remote_file_names: set
        self.unique_local_file_names: set
        self.out_of_sync_local_file_names: set
        self.out_of_sync_remote_file_names: set
        self.synced_files_count: int

    def push(self) -> bool:
        ...

    def pull(self) -> bool:
        ...

    def _normalize_remote_file_names(self, remote_files: Dict[str, Any], 
                                      local_files: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def _local_candidates(self, candidate_path: str) -> Dict[str, str]:
        ...

    def _print_duplicate_file_names(self) -> None:
        ...

    def _print_sync_status(self, success: Dict[str, Any], errors: Dict[str, Any]) -> None:
        ...

    def _save_sync_meta_file(self, upload_results: Dict[str, Any]) -> None:
        ...

    def _handle_unique_remote_files(self) -> bool:
        ...

    def _get_out_of_sync_file_names(self, common_file_names: set) -> set:
        ...

    def _handle_unique_local_files(self) -> bool:
        ...

    def _handle_files_deletion(self, num_files: int, location: str) -> Optional[bool]:
        ...

    def _handle_files_deletion_decision(self, num_files: int, location: str) -> Optional[bool]:
        ...
