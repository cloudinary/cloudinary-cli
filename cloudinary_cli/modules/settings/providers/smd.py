import json
import logging
import fnmatch

import click
import cloudinary

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.api_utils import call_api_with_pagination
from cloudinary_cli.utils.utils import confirm_action

from .smd_table import format_datasource_values, render_smd_fields_table

def summarize_smd_bundle(smd_bundle):
    """
    Summarize an SMD bundle for CLI output.

    Returns:
      - field_rows: list[dict] with keys: external_id, type, datasource_values
      - rules: list[str] of rule names
    """
    field_rows = []
    for f in smd_bundle.get("fields", []) or []:
        if not isinstance(f, dict):
            continue
        external_id = f.get("external_id")
        if not external_id:
            continue
        field_type = f.get("type", "")

        ds_values = ""
        ds = f.get("datasource")
        if isinstance(ds, dict) and isinstance(ds.get("values"), list):
            vals = []
            for v in ds.get("values") or []:
                if not isinstance(v, dict):
                    continue
                # Prefer human-readable value; fall back to external_id.
                vals.append(v.get("value") or v.get("external_id") or "")
            vals = [x for x in vals if x]
            ds_values = format_datasource_values(vals)

        field_rows.append({
            "external_id": external_id,
            "type": field_type,
            "datasource_values": ds_values,
        })

    field_rows.sort(key=lambda r: r["external_id"])
    rules = sorted(
        [r.get("name") for r in smd_bundle.get("rules", []) if isinstance(r, dict) and r.get("name")]
    )
    return field_rows, rules


def export_smd_bundle(field_external_ids=None, rule_names=None, include_related_rules=False):
    """
    Export Structured Metadata settings from the current product environment.
    """
    all_fields = call_api_with_pagination(cloudinary.api.list_metadata_fields, force=True).get("metadata_fields", [])
    all_rules = call_api_with_pagination(cloudinary.api.list_metadata_rules, force=True).get("metadata_rules", [])

    field_external_ids = set(field_external_ids or [])
    rule_names = set(rule_names or [])
    all_rules_selected = "__ALL__" in rule_names
    if all_rules_selected:
        rule_names.discard("__ALL__")

    rules = all_rules
    if (not all_rules_selected) and rule_names:
        rules = _filter_by_name_or_patterns(rules, "name", rule_names)

    fields = all_fields
    if field_external_ids:
        fields = _filter_by_name_or_patterns(all_fields, "external_id", field_external_ids)

    # If user requested rules but did not request fields explicitly,
    # auto-include any referenced fields so the bundle can be applied.
    if (all_rules_selected or rule_names) and not field_external_ids:
        referenced = _referenced_field_ids_from_rules(rules)
        if referenced:
            fields = [f for f in all_fields if f.get("external_id") in referenced]

    # If user requested fields and asked to include related rules, include rules
    # that either apply to these fields or use them in their condition.
    if include_related_rules and field_external_ids:
        related = []
        for r in all_rules:
            applies_to = r.get("metadata_field_id") in field_external_ids
            controlled_by = any(cid in field_external_ids for cid in (r.get("controlling_ids") or []))
            if applies_to or controlled_by:
                related.append(r)

        # Merge with any explicitly selected rules.
        if rule_names:
            chosen = {r.get("name") for r in rules}
            for r in related:
                if r.get("name") not in chosen:
                    rules.append(r)
        else:
            rules = related

        # Ensure all required fields for these rules are included too.
        referenced = set(field_external_ids) | _referenced_field_ids_from_rules(rules)
        fields = [f for f in all_fields if f.get("external_id") in referenced]

    return {"fields": fields, "rules": rules}


def apply_smd_bundle(
    bundle_smd,
    target_options=None,
    dry_run=False,
    force=False,
    field_external_ids=None,
    rule_names=None,
    include_related_rules=False,
    mode="create-missing",
):
    """
    Apply Structured Metadata settings to the target environment.

    Supported modes:
    - create-missing: create only missing items
    - upsert: create missing + update differing
    - sync: upsert + delete items not present in the bundle selection
    """
    mode = (mode or "create-missing").lower()
    if mode not in ("create-missing", "upsert", "sync"):
        raise ValueError(f"Unsupported SMD mode: {mode}")

    kwargs = target_options or {}

    target_fields = _list_target_fields(kwargs)
    target_rules = _list_target_rules(kwargs)

    desired_fields, desired_rules = _desired_from_bundle(
        bundle_smd,
        field_external_ids=field_external_ids,
        rule_names=rule_names,
        include_related_rules=include_related_rules,
    )

    plan = _build_plan(desired_fields, desired_rules, target_fields, target_rules)

    # Reduce plan based on mode
    if mode == "create-missing":
        plan["fields"]["update"] = []
        plan["fields"]["delete"] = []
        plan["rules"]["update"] = []
        plan["rules"]["delete"] = []
    elif mode == "upsert":
        plan["fields"]["delete"] = []
        plan["rules"]["delete"] = []
    # sync keeps everything

    if not any(plan[k][a] for k in ("fields", "rules") for a in ("create", "update", "delete")):
        logger.info("SMD: target already matches the desired selection. Nothing to do.")
        return True

    if not force:
        def _use_color():
            try:
                return click.get_text_stream("stdout").isatty()
            except Exception:
                return False

        use_color = _use_color()

        def _c(s, fg=None, bold=False, dim=False):
            if not use_color:
                return s
            return click.style(s, fg=fg, bold=bold, dim=dim)

        def _colorize_diff_line(line):
            # Heuristics based on our diff line formats.
            if "present in desired only" in line:
                return f"{_c('+', fg='green', bold=True)} {_c(line, fg='green', dim=True)}"
            if "present in target only" in line:
                return f"{_c('-', fg='red', bold=True)} {_c(line, fg='red', dim=True)}"
            if " != " in line:
                return f"{_c('~', fg='yellow', bold=True)} {_c(line, fg='yellow')}"
            return f"{_c('•', fg='white', dim=True)} {line}"

        def _format_items(items, indent="  ", bullet="- ", max_items=20):
            if not items:
                return f"{indent}(none)"
            shown = list(items)[:max_items]
            lines = [f"{indent}{bullet}{x}" for x in shown]
            if len(items) > max_items:
                lines.append(f"{indent}{bullet}… (+{len(items) - max_items} more)")
            return "\n".join(lines)

        def _rule_display_from_target(rule_name):
            r = (target_rules or {}).get(rule_name) or {}
            ext_id = r.get("external_id") or ""
            return f"\"{rule_name}\" ({ext_id})" if ext_id else f"\"{rule_name}\""

        def _rule_display_from_desired(rule_name):
            r = (desired_rules or {}).get(rule_name) or {}
            ext_id = r.get("external_id") or ""
            return f"\"{rule_name}\" ({ext_id})" if ext_id else f"\"{rule_name}\""

        def _format_updates_with_diffs(display_items, diff_lines_by_display_item, indent="  ", bullet="- ", max_items=20):
            if not display_items:
                return f"{indent}(none)"
            shown = list(display_items)[:max_items]
            lines = []
            for item in shown:
                lines.append(f"{indent}{bullet}{item}")
                dl = diff_lines_by_display_item.get(item) or []
                for d in dl:
                    lines.append(f"{indent}    {_colorize_diff_line(d)}")
            if len(display_items) > max_items:
                lines.append(f"{indent}{bullet}… (+{len(display_items) - max_items} more)")
            return "\n".join(lines)

        def _format_section(label, body, none_value="(none)"):
            """
            Render a section as either:
              '<label>: (none)'
            or:
              '<label>:\\n<body>'
            """
            body_str = body or ""
            if body_str.strip() == none_value:
                return f"  {label}: {none_value}\n"
            return f"  {label}:\n{body_str}\n"

        fields_create = plan["fields"]["create"]
        fields_update = plan["fields"]["update"]
        fields_delete = plan["fields"]["delete"]

        rules_create_disp = [_rule_display_from_desired(n) for n in plan["rules"]["create"]]
        rules_update_disp = [_rule_display_from_target(n) for n in plan["rules"]["update"]]
        rules_delete_disp = [_rule_display_from_target(n) for n in plan["rules"]["delete"]]

        debug = logger.isEnabledFor(logging.DEBUG)
        field_diff_by_id = {}
        rule_diff_by_display = {}
        if debug:
            for fid in fields_update:
                d_norm, t_norm = _normalize_field_pair_for_compare(
                    desired_fields.get(fid),
                    target_fields.get(fid),
                )
                diffs = _diff_any(
                    d_norm,
                    t_norm,
                    path="$",
                    max_diffs=40,
                )
                if diffs:
                    field_diff_by_id[fid] = diffs
            for rn in plan["rules"]["update"]:
                target_rule = (target_rules or {}).get(rn)
                disp = _rule_display_from_target(rn)
                diffs = _diff_any(
                    _normalize_rule_for_compare(desired_rules.get(rn)),
                    _normalize_rule_for_compare(target_rule),
                    path="$",
                    max_diffs=40,
                )
                if diffs:
                    rule_diff_by_display[disp] = diffs

        create_lbl = _c("create", fg="green", bold=True)
        update_lbl = _c("update", fg="yellow", bold=True)
        delete_lbl = _c("delete", fg="red", bold=True)

        fields_create_block = _format_items(fields_create)
        fields_update_block = _format_updates_with_diffs(fields_update, field_diff_by_id) if debug else _format_items(fields_update)
        fields_delete_block = _format_items(fields_delete)

        rules_create_block = _format_items(rules_create_disp)
        rules_update_block = _format_updates_with_diffs(rules_update_disp, rule_diff_by_display) if debug else _format_items(rules_update_disp)
        rules_delete_block = _format_items(rules_delete_disp)

        msg = (
            f"{_c('This operation will apply Structured Metadata changes to the target environment:', bold=True)}\n"
            f"- fields: "
            f"{_c('+' + str(len(fields_create)), fg='green', bold=True)} "
            f"{_c('~' + str(len(fields_update)), fg='yellow', bold=True)} "
            f"{_c('-' + str(len(fields_delete)), fg='red', bold=True)}\n"
            f"{_format_section(create_lbl, fields_create_block)}"
            f"{_format_section(update_lbl, fields_update_block)}"
            f"{_format_section(delete_lbl, fields_delete_block)}"
            f"- rules:  "
            f"{_c('+' + str(len(rules_create_disp)), fg='green', bold=True)} "
            f"{_c('~' + str(len(rules_update_disp)), fg='yellow', bold=True)} "
            f"{_c('-' + str(len(rules_delete_disp)), fg='red', bold=True)}\n"
            f"{_format_section(create_lbl, rules_create_block)}"
            f"{_format_section(update_lbl, rules_update_block)}"
            f"{_format_section(delete_lbl, rules_delete_block)}"
            "Continue? (y/N)"
        )
        if not confirm_action(msg):
            logger.info("Stopping.")
            return False

    if dry_run:
        logger.info(
            f"SMD dry-run: fields +{len(plan['fields']['create'])} ~{len(plan['fields']['update'])} -{len(plan['fields']['delete'])}, "
            f"rules +{len(plan['rules']['create'])} ~{len(plan['rules']['update'])} -{len(plan['rules']['delete'])}."
        )
        return True

    # Apply ordering:
    # - delete rules first, then fields
    # - create/update fields first, then rules
    for rule_name in plan["rules"]["delete"]:
        rule_external_id = (target_rules.get(rule_name) or {}).get("external_id") or rule_name
        _delete_rule(rule_external_id, kwargs)

    for field_id in plan["fields"]["delete"]:
        _delete_field(field_id, kwargs)

    for field_id in plan["fields"]["create"]:
        _create_field(desired_fields[field_id], kwargs)
        ok = _sync_field_datasource(
            field_external_id=field_id,
            desired_field=desired_fields[field_id],
            target_field=None,
            mode=mode,
            target_options=kwargs,
            desired_rules=desired_rules,
            target_rules=target_rules,
        )
        if ok is False:
            return False

    for field_id in plan["fields"]["update"]:
        _update_field(field_id, desired_fields[field_id], kwargs)
        ok = _sync_field_datasource(
            field_external_id=field_id,
            desired_field=desired_fields[field_id],
            target_field=target_fields.get(field_id),
            mode=mode,
            target_options=kwargs,
            desired_rules=desired_rules,
            target_rules=target_rules,
        )
        if ok is False:
            return False

    for rule_id in plan["rules"]["create"]:
        _create_rule(desired_rules[rule_id], kwargs)

    for rule_name in plan["rules"]["update"]:
        rule_external_id = (target_rules.get(rule_name) or {}).get("external_id") or rule_name
        _update_rule(rule_external_id, desired_rules[rule_name], kwargs)

    return True


def delete_smd_items(
    target_options=None,
    dry_run=False,
    force=False,
    field_external_ids=None,
    rule_names=None,
    include_related_rules=False,
):
    """
    Delete selected Structured Metadata items from the target environment.

    - Deletes rules first, then fields (API constraint).
    - Selection is explicit: only deletes the provided fields/rules (plus related rules if requested).
    """
    kwargs = target_options or {}

    field_external_ids = set(field_external_ids or [])
    rule_names = set(rule_names or [])

    if not field_external_ids and not rule_names:
        logger.error("SMD delete: nothing selected. Provide --pick smd field ... and/or --pick smd rule ...")
        return False

    target_fields = _list_target_fields(kwargs)
    target_rules = _list_target_rules(kwargs)

    # Expand "all" sentinel selections
    if "__ALL__" in field_external_ids:
        field_external_ids = set(target_fields.keys())
    if "__ALL__" in rule_names:
        rule_names = set(target_rules.keys())

    # Expand wildcard patterns (glob) against current target state
    field_external_ids = _expand_names_with_patterns(set(target_fields.keys()), field_external_ids)
    rule_names = _expand_names_with_patterns(set(target_rules.keys()), rule_names)

    if include_related_rules and field_external_ids:
        for name, r in (target_rules or {}).items():
            applies_to = r.get("metadata_field_id") in field_external_ids
            controlled_by = any(cid in field_external_ids for cid in (r.get("controlling_ids") or []))
            if applies_to or controlled_by:
                rule_names.add(name)

    fields_to_delete = [fid for fid in sorted(field_external_ids) if fid in target_fields]
    missing_fields = [fid for fid in sorted(field_external_ids) if fid not in target_fields]

    rules_to_delete = []
    rule_display = []
    missing_rules = []
    for rn in sorted(rule_names):
        r = target_rules.get(rn)
        if not r:
            missing_rules.append(rn)
        else:
            external_id = r.get("external_id") or rn
            rules_to_delete.append(external_id)
            rule_display.append(f"{rn} ({external_id})")

    if missing_fields:
        logger.warning(f"SMD delete: fields not found (skipping): {', '.join(missing_fields)}")
    if missing_rules:
        logger.warning(f"SMD delete: rules not found (skipping): {', '.join(missing_rules)}")

    if not rules_to_delete and not fields_to_delete:
        logger.info("SMD delete: nothing to delete (all selected items were missing).")
        return True

    if not force:
        def _format_list(items, indent="  ", bullet="  - ", max_items=20):
            if not items:
                return f"{indent}(none)"
            shown = list(items)[:max_items]
            lines = [f"{indent}{bullet}{x}" for x in shown]
            if len(items) > max_items:
                lines.append(f"{indent}{bullet}… (+{len(items) - max_items} more)")
            return "\n".join(lines)

        msg = (
            "This operation will delete Structured Metadata items from the target environment:\n"
            f"- fields: {len(fields_to_delete)}\n"
            f"{_format_list(fields_to_delete)}\n"
            f"- rules:  {len(rules_to_delete)}\n"
            f"{_format_list(rule_display)}\n"
            "Continue? (y/N)"
        )
        if not confirm_action(msg):
            logger.info("Stopping.")
            return False

    if dry_run:
        logger.info(
            f"SMD dry-run delete: fields -{len(fields_to_delete)}, rules -{len(rules_to_delete)}."
        )
        return True

    for rule_external_id in rules_to_delete:
        _delete_rule(rule_external_id, kwargs)
    for field_external_id in fields_to_delete:
        ok = _delete_field(field_external_id, kwargs)
        if ok is False:
            return False

    return True


def _extract_datasource_entries(field):
    """
    Return datasource entries list for a metadata field, or [].
    """
    if not isinstance(field, dict):
        return []
    ds = field.get("datasource")
    if not isinstance(ds, dict):
        return []
    values = ds.get("values")
    if not isinstance(values, list):
        return []
    return [v for v in values if isinstance(v, dict)]


def _datasource_entry_key(entry):
    return entry.get("external_id") or entry.get("value") or ""


def _rules_referencing_options(rules_by_name, field_external_id, option_external_ids):
    """
    Find rule names that reference a specific field option (value) in their condition.

    Returns dict[option_external_id] -> list[rule_name]
    """
    option_external_ids = set(option_external_ids or [])
    if not option_external_ids:
        return {}
    res = {opt: [] for opt in option_external_ids}

    def walk(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    for rule_name, rule in (rules_by_name or {}).items():
        if not isinstance(rule, dict):
            continue
        # 1) Condition references (equals/includes on this field)
        cond = rule.get("condition")
        if cond:
            for node in walk(cond):
                if not isinstance(node, dict):
                    continue
                if node.get("metadata_field_id") != field_external_id:
                    continue

                # equals can be a string or list; includes is list for set fields.
                eq = node.get("equals")
                inc = node.get("includes")
                vals = []
                if isinstance(eq, str):
                    vals.append(eq)
                elif isinstance(eq, list):
                    vals.extend([x for x in eq if isinstance(x, str)])
                if isinstance(inc, list):
                    vals.extend([x for x in inc if isinstance(x, str)])

                for v in vals:
                    if v in res:
                        res[v].append(rule_name)

        # 2) Result references (apply_value / activate_values) when rule applies to this field
        if rule.get("metadata_field_id") == field_external_id:
            result = rule.get("result") or {}
            if isinstance(result, dict):
                apply_value = result.get("apply_value") or {}
                if isinstance(apply_value, dict):
                    v = apply_value.get("value")
                    vals = []
                    if isinstance(v, str):
                        vals.append(v)
                    elif isinstance(v, list):
                        vals.extend([x for x in v if isinstance(x, str)])
                    for x in vals:
                        if x in res:
                            res[x].append(rule_name)

                activate_values = result.get("activate_values")
                # activate_values can be {"external_ids":[...]} or "all"
                if isinstance(activate_values, dict):
                    ex_ids = activate_values.get("external_ids") or []
                    if isinstance(ex_ids, list):
                        for x in ex_ids:
                            if isinstance(x, str) and x in res:
                                res[x].append(rule_name)

    # remove empties and stable sort lists
    res = {k: sorted(v) for k, v in res.items() if v}
    return res


def _sync_field_datasource(field_external_id, desired_field, target_field, mode, target_options, desired_rules=None, target_rules=None):
    """
    Ensure datasource values match desired state.

    Notes:
    - Cloudinary Admin API uses a dedicated datasource update endpoint; updating the field itself doesn't reliably update
      datasource entries.
    - In sync mode, removes datasource entries not present in the desired bundle.
    """
    desired_entries = _extract_datasource_entries(desired_field)
    if not desired_entries:
        return True

    # Upsert desired entries (adds + updates value).
    cloudinary.api.update_metadata_field_datasource(field_external_id, desired_entries, **target_options)
    logger.info(f"SMD: updated datasource entries for field '{field_external_id}' ({len(desired_entries)} entries).")

    # Enforce desired active/inactive state explicitly using datasource endpoints.
    desired_active = []
    desired_inactive = []
    for e in desired_entries:
        ext_id = e.get("external_id")
        if not ext_id:
            continue
        state = (e.get("state") or "active").lower()
        if state == "inactive":
            desired_inactive.append(ext_id)
        else:
            desired_active.append(ext_id)

    if desired_inactive:
        # Cloudinary forbids deactivating/deleting options that are used by metadata rules.
        blockers = _rules_referencing_options(
            desired_rules or target_rules or {},
            field_external_id=field_external_id,
            option_external_ids=set(desired_inactive),
        )
        blocked = set()
        if blockers:
            blocked = {opt for opt in blockers.keys()}
            for opt, rules in blockers.items():
                rule_list = "\n".join([f'- "{rn}"' for rn in rules])
                logger.warning(
                    f"SMD: skipping deactivation of option '{opt}' for field '{field_external_id}' because it is referenced by rule(s):\n{rule_list}"
                )

        to_deactivate = [x for x in desired_inactive if x not in blocked]
        if to_deactivate:
            try:
                cloudinary.api.delete_datasource_entries(field_external_id, to_deactivate, **target_options)
                logger.info(
                    f"SMD: deactivated datasource entries for field '{field_external_id}' ({len(to_deactivate)} entries)."
                )
            except Exception as e:
                msg = str(e)
                if "Can't delete a metadata field option that is used by metadata rules" in msg:
                    logger.error(
                        f"SMD: can't deactivate some datasource entries for field '{field_external_id}' because they are used by metadata rules. "
                        "Update/delete the referencing rules first, or keep these options active."
                    )
                    return False
                raise
    if desired_active:
        cloudinary.api.restore_metadata_field_datasource(field_external_id, desired_active, **target_options)
        logger.info(
            f"SMD: activated datasource entries for field '{field_external_id}' ({len(desired_active)} entries)."
        )

    if (mode or "").lower() == "sync" and target_field:
        target_entries = _extract_datasource_entries(target_field)
        desired_keys = {k for k in (_datasource_entry_key(e) for e in desired_entries) if k}
        to_delete = []
        for e in target_entries:
            key = _datasource_entry_key(e)
            ext_id = e.get("external_id")
            if ext_id and key and key not in desired_keys:
                to_delete.append(ext_id)

        if to_delete:
            # Avoid deleting options still referenced by rules (either in conditions or results).
            blockers = _rules_referencing_options(
                target_rules or desired_rules or {},
                field_external_id=field_external_id,
                option_external_ids=set(to_delete),
            )
            blocked = set(blockers.keys()) if blockers else set()
            if blockers:
                for opt, rules in blockers.items():
                    rule_list = "\n".join([f'- "{rn}"' for rn in rules])
                    logger.warning(
                        f"SMD: skipping deletion of option '{opt}' for field '{field_external_id}' because it is referenced by rule(s):\n{rule_list}"
                    )

            to_delete_safe = [x for x in to_delete if x not in blocked]
            if to_delete_safe:
                try:
                    cloudinary.api.delete_datasource_entries(field_external_id, to_delete_safe, **target_options)
                    logger.info(
                        f"SMD: deleted datasource entries for field '{field_external_id}' ({len(to_delete_safe)} entries)."
                    )
                except Exception as e:
                    msg = str(e)
                    if "Can't delete a metadata field option that is used by metadata rules" in msg:
                        logger.error(
                            f"SMD: can't delete some datasource entries for field '{field_external_id}' because they are used by metadata rules. "
                            "Update/delete the referencing rules first, or keep these options present."
                        )
                        # Non-fatal: we already tried to pre-filter, so just stop trying to delete extras.
                        return True
                    raise

    return True


def _debug_log_diff(kind, identifier, desired, target, max_lines=200):
    """
    DEBUG helper: log a structured diff between desired and target objects.
    """
    if not logger.isEnabledFor(logging.DEBUG):
        return

    diffs = _diff_any(desired, target, path="$", max_diffs=max_lines)
    if not diffs:
        return

    logger.debug(f"{kind} diff for {identifier}:")
    for line in diffs[:max_lines]:
        logger.debug(f"  {line}")
    if len(diffs) > max_lines:
        logger.debug(f"  … (+{len(diffs) - max_lines} more)")


def _diff_any(a, b, path="$", max_diffs=200):
    """
    Return list of human-readable diff lines. Best-effort; aims to be useful, not perfect.
    """
    diffs = []

    def add(msg):
        if len(diffs) < max_diffs:
            diffs.append(msg)

    if a == b:
        return diffs

    if isinstance(a, dict) and isinstance(b, dict):
        a_keys = set(a.keys())
        b_keys = set(b.keys())
        for k in sorted(a_keys - b_keys):
            add(f"{path}.{k}: present in desired only")
        for k in sorted(b_keys - a_keys):
            add(f"{path}.{k}: present in target only")
        for k in sorted(a_keys & b_keys):
            if len(diffs) >= max_diffs:
                break
            av = a.get(k)
            bv = b.get(k)
            if av == bv:
                continue
            # Recurse for nested containers, otherwise show a compact value diff.
            if isinstance(av, (dict, list)) and isinstance(bv, (dict, list)):
                diffs.extend(_diff_any(av, bv, path=f"{path}.{k}", max_diffs=max_diffs - len(diffs)))
            else:
                add(f"{path}.{k}: { _compact(av) } != { _compact(bv) }")
        return diffs

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            add(f"{path}: list length {len(a)} != {len(b)}")

        # Try to align lists of dicts by external_id/value if possible (datasource values).
        if all(isinstance(x, dict) for x in a) and all(isinstance(x, dict) for x in b):
            a_map = {(_datasource_entry_key(x) or str(i)): x for i, x in enumerate(a)}
            b_map = {(_datasource_entry_key(x) or str(i)): x for i, x in enumerate(b)}
            keys = sorted(set(a_map.keys()) | set(b_map.keys()))
            for k in keys:
                if len(diffs) >= max_diffs:
                    break
                if k not in a_map:
                    add(f"{path}[{k}]: present in target only")
                elif k not in b_map:
                    add(f"{path}[{k}]: present in desired only")
                else:
                    if a_map[k] != b_map[k]:
                        diffs.extend(_diff_any(a_map[k], b_map[k], path=f"{path}[{k}]", max_diffs=max_diffs - len(diffs)))
            return diffs

        # Fallback: compare by index
        for i in range(min(len(a), len(b))):
            if len(diffs) >= max_diffs:
                break
            if a[i] != b[i]:
                diffs.extend(_diff_any(a[i], b[i], path=f"{path}[{i}]", max_diffs=max_diffs - len(diffs)))
        return diffs

    # Primitive mismatch
    add(f"{path}: { _compact(a) } != { _compact(b) }")
    return diffs


def _compact(v, max_len=240):
    """
    Compact a value into a single-line string for debug logs.
    """
    try:
        s = json.dumps(v, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(v)
    s = s.replace("\n", "\\n")
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _desired_from_bundle(bundle_smd, field_external_ids=None, rule_names=None, include_related_rules=False):
    all_bundle_fields = _index_by(bundle_smd.get("fields", []), "external_id")
    all_bundle_rules = _index_by(bundle_smd.get("rules", []), "name")

    desired_fields = dict(all_bundle_fields)
    desired_rules = dict(all_bundle_rules)

    if field_external_ids:
        field_external_ids = set(field_external_ids)
        desired_fields = _filter_index_by_name_or_patterns(desired_fields, field_external_ids)

    if rule_names:
        rule_names = set(rule_names)
        all_rules_selected = "__ALL__" in rule_names
        if all_rules_selected:
            rule_names.discard("__ALL__")
        if not all_rules_selected:
            desired_rules = _filter_index_by_name_or_patterns(desired_rules, rule_names)

    if include_related_rules and field_external_ids:
        related_rules = {}
        for name, r in all_bundle_rules.items():
            applies_to = r.get("metadata_field_id") in field_external_ids
            controlled_by = any(cid in field_external_ids for cid in (r.get("controlling_ids") or []))
            if applies_to or controlled_by:
                related_rules[name] = r
        desired_rules.update(related_rules)

    # Ensure required fields for selected rules are included if present in the bundle.
    if desired_rules:
        required_fields = _referenced_field_ids_from_rules(desired_rules.values())
        for fid in required_fields:
            if fid in all_bundle_fields and fid not in desired_fields:
                desired_fields[fid] = all_bundle_fields[fid]

    return desired_fields, desired_rules


def _build_plan(desired_fields, desired_rules, target_fields, target_rules):
    plan = {
        "fields": {"create": [], "update": [], "delete": []},
        "rules": {"create": [], "update": [], "delete": []},
    }

    desired_field_ids = set(desired_fields.keys())
    target_field_ids = set(target_fields.keys())

    desired_rule_ids = set(desired_rules.keys())
    target_rule_ids = set(target_rules.keys())

    plan["fields"]["create"] = sorted(desired_field_ids - target_field_ids)
    plan["rules"]["create"] = sorted(desired_rule_ids - target_rule_ids)

    common_fields = desired_field_ids & target_field_ids
    common_rules = desired_rule_ids & target_rule_ids

    plan["fields"]["update"] = sorted(
        fid for fid in common_fields
        if _fields_need_update(desired_fields[fid], target_fields[fid])
    )
    plan["rules"]["update"] = sorted(
        rid for rid in common_rules
        if _normalize_rule_for_compare(desired_rules[rid]) != _normalize_rule_for_compare(target_rules[rid])
    )

    plan["fields"]["delete"] = sorted(target_field_ids - desired_field_ids)
    plan["rules"]["delete"] = sorted(target_rule_ids - desired_rule_ids)

    # Delete rules before fields (ordering handled in apply). Sorting already stable.
    return plan


def _index_by(items, key):
    res = {}
    for i in items or []:
        if not isinstance(i, dict):
            continue
        k = i.get(key)
        if k is not None:
            res[k] = i
    return res


def _is_pattern(s):
    return isinstance(s, str) and any(ch in s for ch in ("*", "?", "["))


def _expand_names_with_patterns(universe_names, selected):
    """
    Expand wildcard patterns in `selected` against `universe_names`.
    """
    selected = set(selected or [])
    if not selected:
        return set()

    patterns = {x for x in selected if _is_pattern(x)}
    exact = {x for x in selected if not _is_pattern(x)}

    matched = set()
    for p in patterns:
        matched |= set(fnmatch.filter(universe_names, p))

    return exact | matched


def _filter_by_name_or_patterns(items, key, selected):
    """
    Filter list[dict] items by exact names or wildcard patterns for `key`.
    """
    selected = set(selected or [])
    if not selected:
        return list(items or [])
    names = {i.get(key) for i in (items or []) if isinstance(i, dict) and i.get(key)}
    expanded = _expand_names_with_patterns(names, selected)
    return [i for i in (items or []) if isinstance(i, dict) and i.get(key) in expanded]


def _filter_index_by_name_or_patterns(index, selected):
    """
    Filter an index dict[name -> dict] by exact names or wildcard patterns.
    """
    selected = set(selected or [])
    if not selected:
        return dict(index or {})
    expanded = _expand_names_with_patterns(set(index.keys()), selected)
    return {k: v for k, v in (index or {}).items() if k in expanded}


def _strip_dict_keys_deep(obj, forbidden_keys):
    """
    Recursively remove dict keys from nested dict/list structures.
    """
    if isinstance(obj, dict):
        return {
            k: _strip_dict_keys_deep(v, forbidden_keys)
            for k, v in obj.items()
            if k not in forbidden_keys
        }
    if isinstance(obj, list):
        return [_strip_dict_keys_deep(v, forbidden_keys) for v in obj]
    return obj


def _sort_datasource_values(field):
    """
    Stable sort datasource.values (if present) to make comparisons deterministic.
    """
    if not isinstance(field, dict):
        return field
    ds = field.get("datasource")
    if not isinstance(ds, dict):
        return field
    values = ds.get("values")
    if not isinstance(values, list):
        return field
    ds["values"] = sorted(
        [v for v in values if isinstance(v, dict)],
        key=lambda x: ((x.get("external_id") or ""), (x.get("value") or "")),
    )
    field["datasource"] = ds
    return field


def _normalize_field_for_compare(field):
    """
    Blacklist-based normalization for comparing metadata fields.

    We intentionally ignore keys that are non-roundtrippable / create-only / noisy in API responses.
    """
    if not isinstance(field, dict):
        return field
    forbidden = {
        # Not reliably round-trippable (may be create-only and/or computed)
        "lazy_datasource_update",
        # Occasionally present in responses / noisy
        "created_at",
        "updated_at",
    }
    normalized = _strip_dict_keys_deep(field, forbidden)
    if isinstance(normalized, dict):
        normalized = _sort_datasource_values(normalized)
    return normalized


def _normalize_field_pair_for_compare(desired_field, target_field):
    """
    Normalize a (desired, target) field pair for comparison.

    Cloudinary may keep deleted datasource entries around as state=inactive and still return them.
    To avoid perpetual drift, we ignore target-only inactive entries (unless desired explicitly includes them).
    """
    desired_norm = _normalize_field_for_compare(desired_field)
    target_norm = _normalize_field_for_compare(target_field)

    if not (isinstance(desired_norm, dict) and isinstance(target_norm, dict)):
        return desired_norm, target_norm

    desired_entries = _extract_datasource_entries(desired_norm)
    target_entries = _extract_datasource_entries(target_norm)
    if not (desired_entries or target_entries):
        return desired_norm, target_norm

    desired_keys = {k for k in (_datasource_entry_key(e) for e in desired_entries) if k}
    if not desired_keys:
        return desired_norm, target_norm

    filtered_target_entries = []
    for e in target_entries:
        key = _datasource_entry_key(e)
        state = (e.get("state") or "").lower()
        if key not in desired_keys and state == "inactive":
            continue
        filtered_target_entries.append(e)

    # Rebuild datasource values with filtered entries and stable sort.
    ds = desired_norm.get("datasource")
    if isinstance(ds, dict):
        ds["values"] = desired_entries
        desired_norm["datasource"] = ds
        desired_norm = _sort_datasource_values(desired_norm)

    ds_t = target_norm.get("datasource")
    if isinstance(ds_t, dict):
        ds_t["values"] = filtered_target_entries
        target_norm["datasource"] = ds_t
        target_norm = _sort_datasource_values(target_norm)

    return desired_norm, target_norm


def _fields_need_update(desired_field, target_field):
    desired_norm, target_norm = _normalize_field_pair_for_compare(desired_field, target_field)
    return desired_norm != target_norm


def _normalize_rule_for_compare(rule):
    """
    Blacklist-based normalization for comparing metadata rules.

    These keys are either identifiers or server-computed and will never round-trip.
    """
    if not isinstance(rule, dict):
        return rule
    forbidden = {
        "external_id",         # identifier (Cloudinary assigns/returns)
        "condition_signature", # server-computed
        "controlling_ids",     # server-computed
        "position",            # can be normalized by server; avoid perpetual drift
        "created_at",
        "updated_at",
    }
    return _strip_dict_keys_deep(rule, forbidden)


def _referenced_field_ids_from_rules(rules):
    referenced = set()
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        mfid = r.get("metadata_field_id")
        if mfid:
            referenced.add(mfid)
        for cid in r.get("controlling_ids") or []:
            referenced.add(cid)
    return referenced


def _rules_referencing_field(target_rules_by_name, field_external_id):
    """
    Return list of (name, external_id) for rules that reference `field_external_id`
    either as the target field (`metadata_field_id`) or as a controlling id.
    """
    res = []
    for name, r in (target_rules_by_name or {}).items():
        if not isinstance(r, dict):
            continue
        if r.get("metadata_field_id") == field_external_id:
            res.append((name, r.get("external_id") or ""))
            continue
        if field_external_id in (r.get("controlling_ids") or []):
            res.append((name, r.get("external_id") or ""))
    res.sort(key=lambda x: x[0])
    return res


def _list_target_fields(target_options):
    fields = call_api_with_pagination(cloudinary.api.list_metadata_fields, kwargs=target_options, force=True).get(
        "metadata_fields", []
    )
    return _index_by(fields, "external_id")


def _list_target_rules(target_options):
    rules = call_api_with_pagination(cloudinary.api.list_metadata_rules, kwargs=target_options, force=True).get(
        "metadata_rules", []
    )
    return _index_by(rules, "name")


def _create_field(field, target_options):
    # Pass full field dict; Cloudinary SDK filters supported params internally.
    cloudinary.api.add_metadata_field(field, **target_options)
    logger.info(f"SMD: created metadata field '{field.get('external_id')}'.")


def _update_field(field_external_id, field, target_options):
    # Pass full field dict; Cloudinary SDK filters supported params internally.
    cloudinary.api.update_metadata_field(field_external_id, field, **target_options)
    logger.info(f"SMD: updated metadata field '{field_external_id}'.")


def _delete_field(field_external_id, target_options):
    try:
        cloudinary.api.delete_metadata_field(field_external_id, **target_options)
        logger.info(f"SMD: deleted metadata field '{field_external_id}'.")
        return True
    except Exception as e:
        msg = str(e)
        if "Can't delete a metadata field that is used by metadata rules" in msg:
            try:
                target_rules = _list_target_rules(target_options)
                blockers = _rules_referencing_field(target_rules, field_external_id)
            except Exception:
                blockers = []

            if blockers:
                lines = []
                for name, ext_id in blockers:
                    if ext_id:
                        lines.append(f'- "{name}" ({ext_id})')
                    else:
                        lines.append(f'- "{name}"')
                details = "\n".join(lines)
                logger.error(
                    f"SMD: can't delete field '{field_external_id}' because it is still referenced by rule(s):\n"
                    f"{details}\n"
                    "Next: re-run with --smd-include-rules (or explicitly --pick smd rule <name> for each rule) and try again."
                )
                return False
        raise


def _create_rule(rule, target_options):
    # Pass full rule dict; Cloudinary SDK filters supported params internally.
    cloudinary.api.add_metadata_rule(rule, **target_options)
    logger.info(f"SMD: created metadata rule '{rule.get('name')}'.")


def _update_rule(rule_external_id, rule, target_options):
    # Blacklist approach: send the full rule, but strip keys that are either immutable
    # (metadata_field_id), identifiers, or server-computed noise.
    payload = rule if isinstance(rule, dict) else {}
    forbidden = {
        "metadata_field_id",      # immutable (can't update)
        "external_id",            # identifier (provided as path param)
        "condition_signature",    # server-computed
        "controlling_ids",        # server-computed
    }
    payload = {k: v for k, v in payload.items() if k not in forbidden}
    cloudinary.api.update_metadata_rule(rule_external_id, payload, **target_options)
    logger.info(f"SMD: updated metadata rule '{rule_external_id}'.")


def _delete_rule(rule_external_id, target_options):
    cloudinary.api.delete_metadata_rule(rule_external_id, **target_options)
    logger.info(f"SMD: deleted metadata rule '{rule_external_id}'.")
