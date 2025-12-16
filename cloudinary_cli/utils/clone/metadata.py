import cloudinary
import cloudinary.api
from cloudinary_cli.utils.config_utils import config_to_dict
from cloudinary_cli.utils.api_utils import call_api_with_pagination
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import confirm_action
from click import style


def clone_metadata(target_config):
    """
    Clone metadata from the source to the destination.
    """
    target_config = config_to_dict(target_config)
    source_metadata = list_metadata_fields()
    if not source_metadata:
        logger.info(style(f"No metadata found in {cloudinary.config().cloud_name}", fg="yellow"))
        return True

    target_metadata = list_metadata_fields(**target_config)
    if not ensure_metadata_fields(source_metadata, target_metadata, **target_config):
        return False

    source_metadata_rules = list_metadata_rules()
    if not source_metadata_rules:
        logger.info(style(f"No metadata rules found in {cloudinary.config().cloud_name}", fg="yellow"))
        return True

    target_metadata_rules = list_metadata_rules(**target_config)
    if not ensure_metadata_rules(source_metadata_rules, target_metadata_rules, **target_config):
        return False

    return True  # Return True to indicate that the metadata was cloned successfully or False if there were no items to clone.


def list_metadata_fields(**options):
    """
    List metadata fields and return as a dictionary keyed by external_id.
    """
    metadata_fields = call_api_with_pagination(cloudinary.api.list_metadata_fields, kwargs=options, force=True).get('metadata_fields', [])
    return {item['external_id']: item for item in metadata_fields}


def list_metadata_rules(**options):
    """
    List metadata rules and return as a dictionary keyed by name.
    """
    metadata_rules = call_api_with_pagination(cloudinary.api.list_metadata_rules, kwargs=options, force=True).get('metadata_rules', [])
    return {item['name']: item for item in metadata_rules}


def create_metadata_field(item, **options):
    return cloudinary.api.add_metadata_field(item, **options)


def create_metadata_rule(item, **options):
    return cloudinary.api.add_metadata_rule(item, **options)


def deep_diff(obj_source, obj_target):
    diffs = {}
    for k in set(obj_source.keys()).union(obj_target.keys()):
        if obj_source.get(k) != obj_target.get(k):
            diffs[k] = {"json_source": obj_source.get(k), "json_target": obj_target.get(k)}

    return diffs


def _create_and_log_item(func, item, item_type_name, display_name_key, options):
    try:
        res = func(item, **options)
        logger.info(
            style(f"Successfully created {item_type_name} `{res.get(display_name_key)}` to {dict(options)['cloud_name']}",
                  fg="green"))
    except Exception as e:
        logger.error(
            style(f"Error when creating {item_type_name} `{item.get(display_name_key)}` to {dict(options)['cloud_name']}",
                  fg="red"))
        logger.error(e)


def _get_items_to_create(dict_source, dict_target, item_type_name, **options):
    """
    Compare source and target dictionaries to determine items to create.
    """
    items_to_create = list(dict_source.keys() - dict_target.keys())
    common = list(dict_source.keys() & dict_target.keys())

    if not len(items_to_create):
        logger.info(style(
            f"{item_type_name} in `{dict(options)['cloud_name']}` and in `{cloudinary.config().cloud_name}` are identical. "
            f"No {item_type_name} will be cloned",
            fg="yellow"))
        if not confirm_action(
                f"If you had some {item_type_name} in the target environment, "
                f"new values from the source environment won't be cloned.\n"
                f"Would you like to still proceed with the cloning of assets? (y/N).\n"):
            logger.info("Stopping.")
            return None, None
        else:
            logger.info("Continuing.")
    else:
        logger.info(style(
            f"{items_to_create} are only in `{dict(options)['cloud_name']}` and will be cloned to `{cloudinary.config().cloud_name}`.",
            fg="blue"))
        if not confirm_action(
                f"You have a {item_type_name} mismatch between the source and target environment.\n"
                f"Confirming this action will create the missing {item_type_name} and their values.\n"
                f"If you currently have some {item_type_name} in the target environment, "
                f"new values from the source environment won't be cloned.\n"
                f"Continue? (y/N)"):
            logger.info("Stopping.")
            return None, None
        else:
            logger.info("Continuing.")

    return items_to_create, dict_source, common


def ensure_metadata_fields(source, target, **options):
    items_to_create, dict_source, common = _get_items_to_create(
        source, target, "metadata fields", **options)

    if items_to_create is None:
        return False

    if len(items_to_create):
        logger.info(style(
            f"Copying {len(items_to_create)} metadata fields from {cloudinary.config().cloud_name} to {dict(options)['cloud_name']}",
            fg="blue"))
        for field in items_to_create:
            _create_and_log_item(create_metadata_field, dict_source[field], 'metadata field', 'label', options)

    # for Phase 3
    # diffs = {}
    # for id_ in common:
    #    if dict_source[id_] != dict_target[id_]:
    #        diffs[id_] = deep_diff(dict_source[id_], dict_target[id_])
    #
    # return {
    #    "only_in_json_source": only_in_source,
    #    "differences": diffs
    # }

    return True


def ensure_metadata_rules(source, target, **options):
    items_to_create, dict_source, common = _get_items_to_create(source, target, "metadata rules", **options)

    if items_to_create is None:
        return False

    if len(items_to_create):
        logger.info(style(
            f"Copying {len(items_to_create)} metadata rules from {cloudinary.config().cloud_name} to {dict(options)['cloud_name']}",
            fg="blue"))
        for rule in items_to_create:
            _create_and_log_item(create_metadata_rule, dict_source[rule], 'metadata rule', 'name', options)

    # for Phase 3
    # diffs = {}
    # for id_ in common:
    #    if dict_source[id_] != dict_target[id_]:
    #        diffs[id_] = deep_diff(dict_source[id_], dict_target[id_])
    #
    # return {
    #    "only_in_json_source": only_in_source,
    #    "differences": diffs
    # }

    return True
