import click


SUPPORTED_PICK_GROUPS = ("smd",)
SUPPORTED_SMD_PICK_KINDS = ("field", "rule")
SMD_PICK_ALL_SENTINEL = "__ALL__"


def parse_picks(picks):
    """
    Parse hierarchical selections passed via --pick <group> <kind> <value>.

    Returns:
      - selected_components: list[str]
      - smd_fields: list[str]
      - smd_rules: list[str]
    """
    if not picks:
        return None, None, None

    groups = set()
    smd_fields = []
    smd_rules = []

    for group, kind, value in picks:
        groups.add(group)
        if group not in SUPPORTED_PICK_GROUPS:
            raise click.UsageError(
                f"Unsupported pick group '{group}'. Supported: {', '.join(SUPPORTED_PICK_GROUPS)}"
            )

        if group == "smd":
            if kind not in SUPPORTED_SMD_PICK_KINDS:
                raise click.UsageError(
                    f"Unsupported pick kind '{kind}' for group 'smd'. Supported: {', '.join(SUPPORTED_SMD_PICK_KINDS)}"
                )
            if kind == "field":
                # "*" means all. Other patterns (e.g. "prefix_*") are treated as wildcards later.
                if value in ("*", "all"):
                    smd_fields.append(SMD_PICK_ALL_SENTINEL)
                else:
                    smd_fields.append(value)
            elif kind == "rule":
                # "*" means all. Other patterns (e.g. "*Nested*") are treated as wildcards later.
                if value in ("*", "all"):
                    smd_rules.append(SMD_PICK_ALL_SENTINEL)
                else:
                    smd_rules.append(value)

    selected_components = sorted(groups)
    return selected_components, smd_fields, smd_rules
