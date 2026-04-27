"""
Settings providers.

Each provider implements the uniform contract documented in
settings-design.md §3.1:

    COMPONENT          - component key (e.g. "smd")
    PICK_KINDS         - tuple of supported --pick kinds for this component
    PICK_ALL_SENTINEL  - value used to represent "all" within the component

    export_bundle(*, picks=None, related=None) -> dict
    summarize_bundle(bundle) -> list[str] | tuple
    apply_bundle(bundle, *, target_options=None, picks=None, related=None,
                 mode="create-missing", dry_run=False, force=False) -> bool
    delete_items(*, target_options=None, picks=None, related=None,
                 dry_run=False, force=False) -> bool   # optional
"""
from . import smd, transformations, upload_presets, streaming_profiles, upload_mappings, config


# Apply order (settings-design.md §3.4). Items earlier in the list have no
# downstream dependencies; items later may reference earlier ones.
APPLY_ORDER = (
    "upload_mappings",
    "streaming_profiles",
    "transformations",
    "smd",          # fields then rules (handled inside the provider)
    "upload_presets",
    "config",       # never auto-applied; included for completeness
)


PROVIDERS = {
    "smd": smd,
    "transformations": transformations,
    "upload_presets": upload_presets,
    "streaming_profiles": streaming_profiles,
    "upload_mappings": upload_mappings,
    "config": config,
}


# Components that participate in the standard save/restore/clone flows.
# `config` is captured at save but skipped on apply.
ALL_COMPONENTS = tuple(PROVIDERS.keys())
DEFAULT_COMPONENTS = (
    "smd",
    "transformations",
    "upload_presets",
    "streaming_profiles",
    "upload_mappings",
    "config",
)


def get_provider(component):
    return PROVIDERS.get(component)


def supports_delete(component) -> bool:
    p = get_provider(component)
    return p is not None and hasattr(p, "delete_items")


def list_components_status():
    """
    Return a list of dicts describing each component for `cld settings components`.
    """
    rows = []
    for name in ALL_COMPONENTS:
        p = PROVIDERS[name]
        rows.append({
            "component": name,
            "pick_kinds": list(getattr(p, "PICK_KINDS", ())),
            "pick_all_sentinel": getattr(p, "PICK_ALL_SENTINEL", None),
            "supports_delete": hasattr(p, "delete_items"),
            "applicable": name != "config",
        })
    return rows
