import cloudinary
from cloudinary_cli.utils.config_utils import config_to_dict
from cloudinary_cli.utils.api_utils import call_api
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import confirm_action, compare_dicts
from click import style

METADATA_FIELDS = "fields"
METADATA_RULES = "rules"
COMPARE_KEY_FIELDS = "external_id"
COMPARE_KEY_RULES = "name"
METADATA_TYPE_SINGULAR = {
    "fields": "field",
    "rules": "rule"
}
METADATA_API_METHODS = {
    "fields": cloudinary.api.add_metadata_field,
    "rules": cloudinary.api.add_metadata_rule
}

def clone_metadata(config, force):
    """Clone metadata fields and rules from source to target."""
    target_config = config_to_dict(config)
    
    # Clone fields (required)
    fields_result = _clone_metadata_type(METADATA_FIELDS, COMPARE_KEY_FIELDS, target_config, force)
    if fields_result is False:
        return False
    
    # Clone rules (optional)
    rules_result = _clone_metadata_type(METADATA_RULES, COMPARE_KEY_RULES, target_config, force)
    if rules_result is False:
        return False
    
    return True

def _clone_metadata_type(item_type, compare_key, target_config, force):
    """
    Generic function to clone a metadata type (fields or rules).
    
    :param item_type: 'fields' or 'rules'
    :param compare_key: Key to use for comparison ('external_id' or 'name')
    :param target_config: Target configuration dict
    :param force: Skip confirmation if True
    :return: True on success, False on failure, None if nothing to clone
    """
    source_cloud = cloudinary.config().cloud_name
    target_cloud = target_config['cloud_name']
    
    # List source items
    logger.info(style(f"Listing metadata {item_type} in `{source_cloud}`.", fg="blue"))
    source_items = list_metadata_items(item_type)
    
    if not source_items:
        logger.info(style(f"No metadata {item_type} found in `{source_cloud}`.", fg="yellow"))
        return False
    
    logger.info(style(f"{len(source_items)} metadata {item_type} found in `{source_cloud}`.", fg="green"))
    
    # List target items
    logger.info(style(f"Listing metadata {item_type} in `{target_cloud}`.", fg="blue"))
    target_items = list_metadata_items(item_type, **target_config)
    logger.info(style(f"{len(target_items)} metadata {item_type} found in `{target_cloud}`.", fg="green"))
    
    # Compare and sync
    source_map, only_in_source, common = compare_dicts(source_items, target_items, compare_key)
    return sync_metadata_items(source_map, only_in_source, common, item_type, force, **target_config)

def list_metadata_items(item_type, **options):
    """
    List metadata fields or rules.
    
    :param item_type: Either 'fields' or 'rules'
    :param options: Cloudinary API options (cloud_name, api_key, etc.)
    :return: List of metadata items
    """
    api_method = getattr(cloudinary.api, f'list_metadata_{item_type}')
    res = api_method(**options)
    return res.get(f'metadata_{item_type}', [])

def sync_metadata_items(source_metadata_items, only_in_source_items, common_items, item_type, force, **options):
    source_cloud = cloudinary.config().cloud_name
    target_cloud = options['cloud_name']
    succeeded = []
    failed = []

    
    if not only_in_source_items:
        logger.info(style(
            f"All metadata {item_type} from `{source_cloud}` already exist in `{target_cloud}`. "
            f"No metadata {item_type} cloning needed.", 
            fg="yellow"
        ))
        return True
    
    logger.info(style(
        f"Metadata {item_type} {only_in_source_items} will be cloned from `{source_cloud}` to `{target_cloud}`.", 
        fg="yellow"
    ))
    
    if common_items:
        logger.info(style(
            f"Metadata {item_type} {list(common_items)} exist in both clouds and will be skipped.", 
            fg="yellow"
        ))
    if not force:
        if not confirm_action(
            f"Based on the analysis above, \n"
            f"The module will now copy the metadata {item_type} from {cloudinary.config().cloud_name} to {dict(options)['cloud_name']}.\n"
            f"Continue? (y/N)"):
            logger.info("Stopping.")
            return False
        else:
            logger.info("Continuing. You may use the -F "
                        "flag to skip confirmation.")

    add_method = METADATA_API_METHODS.get(item_type)
    singular = METADATA_TYPE_SINGULAR.get(item_type)
    
    for key_field in only_in_source_items:
        try:
            add_method(source_metadata_items[key_field], **options)
            succeeded.append(key_field)
            logger.info(style(f"Successfully created metadata {singular} `{key_field}` in `{target_cloud}`", fg="green"))
        except Exception as e:
            failed.append((key_field, str(e)))
            logger.error(style(
                f"Failed to create metadata  {singular} `{key_field}` in `{target_cloud}`: {e}", 
                fg="red"
            ))
    
    # Summary
    if failed:
        logger.warning(style(
            f"Cloned {len(succeeded)}/{len(only_in_source_items)} {item_type} successfully. "
            f"{len(failed)} failed.", 
            fg="yellow"
        ))
        return False  # Or consider partial success handling
    
    if succeeded:
        logger.info(style(f"Successfully cloned {len(succeeded)} metadata {item_type}.", fg="green"))
    
    return True