"""
Selection model: `--pick <group> <kind> <value>` (repeatable).

Groups equal component keys; kinds and `*`/`all` sentinels are documented
in settings-design.md §3.3. Wildcards (`*`, `?`, `[abc]`) are resolved with
fnmatch at apply time.
"""
import click


SUPPORTED_PICK_GROUPS = (
    "smd",
    "transformations",
    "upload_presets",
    "streaming_profiles",
    "upload_mappings",
)

SUPPORTED_SMD_PICK_KINDS = ("field", "rule")
SUPPORTED_TRANSFORMATIONS_PICK_KINDS = ("name",)
SUPPORTED_UPLOAD_PRESETS_PICK_KINDS = ("name",)
SUPPORTED_STREAMING_PROFILES_PICK_KINDS = ("name",)
SUPPORTED_UPLOAD_MAPPINGS_PICK_KINDS = ("folder",)

SMD_PICK_ALL_SENTINEL = "__ALL__"
TRANSFORMATIONS_PICK_ALL_SENTINEL = "__ALL_TRANSFORMATIONS__"
UPLOAD_PRESETS_PICK_ALL_SENTINEL = "__ALL_UPLOAD_PRESETS__"
STREAMING_PROFILES_PICK_ALL_SENTINEL = "__ALL_STREAMING_PROFILES__"
UPLOAD_MAPPINGS_PICK_ALL_SENTINEL = "__ALL_UPLOAD_MAPPINGS__"


def _expand(value, all_sentinel):
    if value in ("*", "all"):
        return all_sentinel
    return value


def parse_picks(picks):
    """
    Parse hierarchical selections passed via --pick <group> <kind> <value>.

    Returns a `Picks` namedtuple-like dict with one key per component plus
    `selected_components`. Lists are returned in source order, with `*`/`all`
    expanded to the corresponding sentinel.

    Backwards-compat: callers that used the legacy 4-tuple
    `(selected_components, smd_fields, smd_rules, transformation_names)`
    keep working via `Picks.__iter__` (yields exactly those 4 in that order).
    """
    if not picks:
        return Picks(selected_components=None)

    groups = set()
    smd_fields = []
    smd_rules = []
    transformation_names = []
    upload_preset_names = []
    streaming_profile_names = []
    upload_mapping_folders = []

    for group, kind, value in picks:
        if group not in SUPPORTED_PICK_GROUPS:
            raise click.UsageError(
                f"Unsupported pick group '{group}'. Supported: {', '.join(SUPPORTED_PICK_GROUPS)}"
            )
        groups.add(group)

        if group == "smd":
            if kind not in SUPPORTED_SMD_PICK_KINDS:
                raise click.UsageError(
                    f"Unsupported pick kind '{kind}' for group 'smd'. "
                    f"Supported: {', '.join(SUPPORTED_SMD_PICK_KINDS)}"
                )
            (smd_fields if kind == "field" else smd_rules).append(_expand(value, SMD_PICK_ALL_SENTINEL))
            continue

        if group == "transformations":
            if kind not in SUPPORTED_TRANSFORMATIONS_PICK_KINDS:
                raise click.UsageError(
                    f"Unsupported pick kind '{kind}' for group 'transformations'. "
                    f"Supported: {', '.join(SUPPORTED_TRANSFORMATIONS_PICK_KINDS)}"
                )
            transformation_names.append(_expand(value, TRANSFORMATIONS_PICK_ALL_SENTINEL))
            continue

        if group == "upload_presets":
            if kind not in SUPPORTED_UPLOAD_PRESETS_PICK_KINDS:
                raise click.UsageError(
                    f"Unsupported pick kind '{kind}' for group 'upload_presets'. "
                    f"Supported: {', '.join(SUPPORTED_UPLOAD_PRESETS_PICK_KINDS)}"
                )
            upload_preset_names.append(_expand(value, UPLOAD_PRESETS_PICK_ALL_SENTINEL))
            continue

        if group == "streaming_profiles":
            if kind not in SUPPORTED_STREAMING_PROFILES_PICK_KINDS:
                raise click.UsageError(
                    f"Unsupported pick kind '{kind}' for group 'streaming_profiles'. "
                    f"Supported: {', '.join(SUPPORTED_STREAMING_PROFILES_PICK_KINDS)}"
                )
            streaming_profile_names.append(_expand(value, STREAMING_PROFILES_PICK_ALL_SENTINEL))
            continue

        if group == "upload_mappings":
            if kind not in SUPPORTED_UPLOAD_MAPPINGS_PICK_KINDS:
                raise click.UsageError(
                    f"Unsupported pick kind '{kind}' for group 'upload_mappings'. "
                    f"Supported: {', '.join(SUPPORTED_UPLOAD_MAPPINGS_PICK_KINDS)}"
                )
            upload_mapping_folders.append(_expand(value, UPLOAD_MAPPINGS_PICK_ALL_SENTINEL))
            continue

    return Picks(
        selected_components=sorted(groups),
        smd_fields=smd_fields,
        smd_rules=smd_rules,
        transformation_names=transformation_names,
        upload_preset_names=upload_preset_names,
        streaming_profile_names=streaming_profile_names,
        upload_mapping_folders=upload_mapping_folders,
    )


class Picks:
    """
    Tiny container for parsed selections.

    Iterable for legacy 4-tuple unpacking:
        selected_components, smd_fields, smd_rules, transformation_names = parse_picks(...)
    """
    __slots__ = (
        "selected_components",
        "smd_fields",
        "smd_rules",
        "transformation_names",
        "upload_preset_names",
        "streaming_profile_names",
        "upload_mapping_folders",
    )

    def __init__(
        self,
        selected_components=None,
        smd_fields=None,
        smd_rules=None,
        transformation_names=None,
        upload_preset_names=None,
        streaming_profile_names=None,
        upload_mapping_folders=None,
    ):
        self.selected_components = selected_components
        self.smd_fields = smd_fields
        self.smd_rules = smd_rules
        self.transformation_names = transformation_names
        self.upload_preset_names = upload_preset_names
        self.streaming_profile_names = streaming_profile_names
        self.upload_mapping_folders = upload_mapping_folders

    def __iter__(self):
        # Legacy 4-tuple unpacking order.
        yield self.selected_components
        yield self.smd_fields
        yield self.smd_rules
        yield self.transformation_names

    def __getitem__(self, idx):
        return tuple(iter(self))[idx]

    def for_component(self, component):
        """
        Return the raw pick list for a component, or None.
        """
        return {
            "smd": (self.smd_fields, self.smd_rules),
            "transformations": self.transformation_names,
            "upload_presets": self.upload_preset_names,
            "streaming_profiles": self.streaming_profile_names,
            "upload_mappings": self.upload_mapping_folders,
        }.get(component)
