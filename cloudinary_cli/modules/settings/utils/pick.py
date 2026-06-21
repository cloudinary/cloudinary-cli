"""
Selection model: `--pick <group> <kind> <value>` (repeatable).

Groups equal component keys; kinds and `*`/`all` sentinels are documented
in settings-design.md §3.3. Wildcards (`*`, `?`, `[abc]`) are resolved with
fnmatch at apply time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

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

SMD_PICK_ALL_SENTINEL = "__ALL_SMD__"
TRANSFORMATIONS_PICK_ALL_SENTINEL = "__ALL_TRANSFORMATIONS__"
UPLOAD_PRESETS_PICK_ALL_SENTINEL = "__ALL_UPLOAD_PRESETS__"
STREAMING_PROFILES_PICK_ALL_SENTINEL = "__ALL_STREAMING_PROFILES__"
UPLOAD_MAPPINGS_PICK_ALL_SENTINEL = "__ALL_UPLOAD_MAPPINGS__"


@dataclass(frozen=True, slots=True)
class Picks:
    """Parsed `--pick` selections, indexed per component."""
    selected_components: Optional[List[str]] = None
    smd_fields: List[str] = field(default_factory=list)
    smd_rules: List[str] = field(default_factory=list)
    transformation_names: List[str] = field(default_factory=list)
    upload_preset_names: List[str] = field(default_factory=list)
    streaming_profile_names: List[str] = field(default_factory=list)
    upload_mapping_folders: List[str] = field(default_factory=list)

    def for_component(self, component: str) -> Union[List[str], Tuple[List[str], List[str]], None]:
        return {
            "smd": (self.smd_fields, self.smd_rules),
            "transformations": self.transformation_names,
            "upload_presets": self.upload_preset_names,
            "streaming_profiles": self.streaming_profile_names,
            "upload_mappings": self.upload_mapping_folders,
        }.get(component)


def _expand(value, all_sentinel):
    if value in ("*", "all"):
        return all_sentinel
    return value


def parse_picks(picks):
    """
    Parse hierarchical selections passed via --pick <group> <kind> <value>.

    Returns a `Picks` instance.
    """
    if not picks:
        return Picks(selected_components=None)

    groups = set()
    smd_fields: List[str] = []
    smd_rules: List[str] = []
    transformation_names: List[str] = []
    upload_preset_names: List[str] = []
    streaming_profile_names: List[str] = []
    upload_mapping_folders: List[str] = []

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
