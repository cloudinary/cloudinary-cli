import cloudinary
from cloudinary_cli.utils.config_utils import config_to_dict
from cloudinary_cli.utils.api_utils import handle_auto_pagination
from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import confirm_action
from click import style

def clone_metadata(config):
    """
    Clone metadata from the source to the destination.
    """
    target_config = config_to_dict(config)
    source_metadata = list_metadata_items("metadata_fields")
    if source_metadata.get('metadata_fields'):
        target_metadata = list_metadata_items("metadata_fields", **target_config)
        fields_compare = compare_create_metadata_items(source_metadata, target_metadata, key="metadata_fields", **target_config)
        if not fields_compare:
            return False
        else:
            source_metadata_rules = list_metadata_items("metadata_rules")
            if source_metadata_rules.get('metadata_rules'):
                target_metadata_rules = list_metadata_items("metadata_rules", **target_config)
                rules_compare = compare_create_metadata_items(source_metadata_rules,target_metadata_rules, key="metadata_rules", id_field="name", **target_config)
                if not rules_compare:
                    return False
            else:
                logger.info(style(f"No metadata rules found in {cloudinary.config().cloud_name}", fg="yellow"))
    else:
        logger.info(style(f"No metadata found in {cloudinary.config().cloud_name}", fg="yellow"))

    return True  # Return True to indicate that the metadata was cloned successfully or False if there were no items to clone.

def list_metadata_items(method_key, **options):
    if method_key == 'metadata_fields':
        res = cloudinary.api.list_metadata_fields(**options)
        res = handle_auto_pagination(res, cloudinary.api.list_metadata_fields, options, None, force=True, filter_fields="")
    else:
        res = cloudinary.api.list_metadata_rules(**options)
        res = handle_auto_pagination(res, cloudinary.api.list_metadata_rules, options, None, force=True, filter_fields="")

    return res

def create_metadata_items(api_method_name, item, **options):
    if api_method_name == 'add_metadata_field':
        res = cloudinary.api.add_metadata_field(item, **options)
    else:
        res = cloudinary.api.add_metadata_rule(item, **options)
    return res

def deep_diff(obj_source, obj_target):
    diffs = {}
    for k in set(obj_source.keys()).union(obj_target.keys()):
        if obj_source.get(k) != obj_target.get(k):
            diffs[k] = {"json_source": obj_source.get(k), "json_target": obj_target.get(k)}
    
    return diffs


def compare_create_metadata_items(json_source, json_target, key, id_field = "external_id", **options):
    list_source = {item[id_field]: item for item in json_source.get(key, [])}
    list_target = {item[id_field]: item for item in json_target.get(key, [])}

    only_in_source = list(list_source.keys() - list_target.keys())
    common = list_source.keys() & list_target.keys()

    if not len(only_in_source):
        logger.info(style(f"{(' '.join(key.split('_')))} in `{dict(options)['cloud_name']}` and in `{cloudinary.config().cloud_name}` are identical. No {(' '.join(key.split('_')))} will be cloned", fg="yellow"))
        if not confirm_action(
            f"If you had some {key} in the target environment, "
            f"new values from the source environment won't be cloned.\n"
            f"Would you like to still proceed with the cloning of assets? (y/N).\n"):
            logger.info("Stopping.")
            return False
        else:
            logger.info("Continuing.")
    else:
        logger.info(style(f"{only_in_source} are only in `{dict(options)['cloud_name']}` and will be cloned to `{cloudinary.config().cloud_name}`.", fg="blue"))
        if not confirm_action(
            f"You have a {key} mismatch between the source and target environment.\n"
            f"Confirming this action will create the missing {key} and their values.\n"
            f"If you currently have some {key} in the target environment, "
            f"new values from the source environment won't be cloned.\n"
            f"Continue? (y/N)"):
            logger.info("Stopping.")
            return False
        else:
            logger.info("Continuing.")
            logger.info(style(f"Copying {len(only_in_source)} {(' '.join(key.split('_')))} from {cloudinary.config().cloud_name} to {dict(options)['cloud_name']}", fg="blue"))
            for key_field in only_in_source:
                if key == 'metadata_fields':
                    try:
                        res = create_metadata_items('add_metadata_field', list_source[key_field], **options)
                        logger.info(style(f"Successfully created {(' '.join(key.split('_')))[:-1]} `{res.get('label')}` to {dict(options)['cloud_name']}", fg="green"))
                    except Exception as e:
                        logger.error(style(f"Error when creating {(' '.join(key.split('_')))[:-1]} `{res.get('label')}`` to {dict(options)['cloud_name']}", fg="red"))
                else:
                    try:
                        res = create_metadata_items('add_metadata_rule', list_source[key_field],**options)
                        logger.info(style(f"Successfully created {(' '.join(key.split('_')))[:-1]} `{res.get('name')}` to {dict(options)['cloud_name']}", fg="green"))
                    except Exception as e:
                        logger.error(style(f"Error when creating {(' '.join(key.split('_')))[:-1]} `{res.get('name')}` to {dict(options)['cloud_name']}", fg="red"))
            
    # for Phase 3
    #diffs = {}
    #for id_ in common:
    #    if list_source[id_] != list_target[id_]:
    #        diffs[id_] = deep_diff(list_source[id_], list_target[id_])

    #return {
    #    "only_in_json_source": only_in_source,
    #    "differences": diffs 
    #}
    return True  # Return True to indicate that the metadata items were compared and created successfully.