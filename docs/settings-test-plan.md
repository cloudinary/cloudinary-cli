# `cld settings` — Test plan

A coverage matrix, regression-test list, and live integration harness for the
`cloudinary_cli/modules/settings/` module. Tracks the work scheduled by
[`settings-fix-plan.md`](settings-fix-plan.md) and the architecture proposed
in [`settings-redesign.md`](settings-redesign.md).

> **See also:**
> - [`settings.md`](settings.md) — end-user guide.
> - [`settings-design.md`](settings-design.md) — current technical design.
> - [`settings-implementation.md`](settings-implementation.md) — current
>   maintainer notes.
> - [`settings-fix-plan.md`](settings-fix-plan.md) — phased remediation plan;
>   each acceptance-criterion bullet links back into this doc.
> - [`settings-redesign.md`](settings-redesign.md) — new internal architecture.

Status: proposed.
Owner: feature/settings.
Scope: `cloudinary_cli/modules/settings/` and `test/test_modules/test_cli_settings*.py`.

---

## 1. Test taxonomy

We run four tiers, gated by external dependencies:

| Tier | Where | Runs in | Deps |
|---|---|---|---|
| Unit (engine) | `test/test_modules/test_settings_engine_*.py` | PR pipeline | none — `cloudinary.api.*` mocked |
| Unit (resource specs) | `test/test_modules/test_settings_resources_*.py` | PR pipeline | none |
| CLI / snapshot / store | `test/test_modules/test_cli_settings*.py` | PR pipeline | filesystem |
| Live integration | `test/integration/settings/test_*.py` | nightly | real Cloudinary credentials |

Coverage targets:

- ≥ 95 % branch coverage on `engine/*` and `snapshot/*`.
- ≥ 90 % branch coverage on each `resources/*.py`.
- 100 % of public CLI commands exercised by at least one CLI test.
- Every bug from [`settings-fix-plan.md`](settings-fix-plan.md) §3 has a named
  regression test in §3 below.

---

## 2. Coverage matrix

The matrix is **resource × mode × picks × source × dry-run/apply**. "Source"
distinguishes export-path (live account) from snapshot-path (file on disk).

A cell is `t` when at least one test exercises it, `-` when intentionally
unsupported, blank when missing today and to be added.

### 2.1 Save path (export)

| resource | full | picks | wildcard picks | virgin account | non-empty account |
|---|---|---|---|---|---|
| smd_fields | t | t | t | t | t |
| smd_rules | t | t | t | t | t |
| transformations | t | | | | t |
| upload_presets | t | | | | t |
| streaming_profiles | t | | | (must be 0 overridden_builtins after fix) | t |
| upload_mappings | t | | | | t |
| config | t | - | - | t | t |

Gaps to fill:

- Wildcard pick coverage for transformations / upload_presets /
  streaming_profiles / upload_mappings.
- Virgin-account assertions for non-SMD resources (matters for the streaming
  profile defaults bug).

### 2.2 Apply path (restore / clone)

For each resource, all three modes plus dry-run.

| resource | mode=create-missing | mode=upsert | mode=sync | dry-run | with picks | empty bundle |
|---|---|---|---|---|---|---|
| smd_fields | t | t | t | t | t | t |
| smd_rules | t | t | t | t | t | t |
| transformations | t | t | | t | | |
| upload_presets | t | t | | t | | |
| streaming_profiles | t | t | | t | | |
| upload_mappings | t | t | | t | | |
| config | - | - | - | t | - | t |

Gaps to fill:

- `mode=sync` for the four newer resources (delete bucket coverage).
- "with picks" tests for non-SMD resources, including the regression for
  diff-with-picks delete bucket (§3.3).
- Empty-bundle behavior across the board (today only SMD has it).

### 2.3 Diff path

| resource | empty target | partial drift | full drift | with picks |
|---|---|---|---|---|
| smd_fields | t | t | t | t |
| smd_rules | t | t | t | t |
| transformations | | | t | |
| upload_presets | | | t | |
| streaming_profiles | | | t | |
| upload_mappings | | | t | |
| config | t | t | - | - |

Gaps to fill:

- "with picks" diff for non-SMD resources is the §3.3 regression.

### 2.4 Delete path (per-component admin subcommands)

| resource | argv names | --pick names | --pick all-sentinel | wildcard | not-found | with rules-aware deletion |
|---|---|---|---|---|---|---|
| smd_fields | t | t | t | t | t | t |
| smd_rules | t | t | t | t | t | - |
| transformations | t | t | t | | t | - |
| upload_presets | t | t | t | | t | - |
| streaming_profiles (custom) | t | t | t | | t | - |
| streaming_profiles (built-in, no flag) | t (must error) | | | | | - |
| streaming_profiles (built-in, with flag) | t | | | | | - |
| upload_mappings | t | t | t | | t | - |
| config | - | - | - | - | - | - |

Gaps to fill:

- Wildcard delete for non-SMD resources.

### 2.5 Snapshot envelope and store

- `make_envelope` / `finalize_envelope` round-trip — covered.
- `load_snapshot` rejects unknown `schema_version` — §3.1.
- `previous_serial_for_lineage` boundary cases — covered.
- Single-file save/load round-trip — covered.
- Dirstore round-trip — covered (`test_dirstore_round_trip`).
- Dirstore prunes stale component files — §3.5.
- Dirstore preserves non-component files — §3.5.
- `list_settings_store_entries` filters by cloud, returns enriched rows when
  asked — partial; add JSON-output assertion.

### 2.6 Picks parsing

- `parse_picks` accepts every supported group/kind combination — covered.
- `parse_picks` rejects unknown groups — covered.
- `parse_picks` rejects unknown kinds — covered.
- `parse_picks` cross-validates `--component` vs picks — §3.7.
- `Picks` is a slotted dataclass after Phase 0 — §3.1.

---

## 3. Bug regression tests

One named test per issue from [`settings-fix-plan.md`](settings-fix-plan.md).
Test names are proposed; bracketed code is suggested location.

### 3.1 v1/v2 collapse

**`test_envelope_load_rejects_unknown_schema_version`**
[`test/test_modules/test_cli_settings.py`]

```python
def test_envelope_load_rejects_unknown_schema_version():
    from cloudinary_cli.modules.settings.snapshot.envelope import load_snapshot
    with pytest.raises(click.UsageError, match="schema_version"):
        load_snapshot({"schema_version": 2, "name": "x"})
    with pytest.raises(click.UsageError, match="schema_version"):
        load_snapshot({"schema_version": 0, "name": "x"})
```

**`test_envelope_make_uses_schema_version_one`**

```python
def test_envelope_make_uses_schema_version_one():
    env = make_envelope(name="alpha", cloud_name="demo", components=["smd"])
    assert env["schema_version"] == 1
    assert "lineage" not in env  # dropped per redesign §6
    assert "serial" not in env
```

**`test_picks_is_slotted_dataclass`**

```python
def test_picks_is_slotted_dataclass():
    from cloudinary_cli.modules.settings.engine.picks import Picks
    assert dataclasses.is_dataclass(Picks)
    assert "__dict__" not in Picks.__slots__  # slotted
    with pytest.raises(TypeError):
        # No __iter__ -> not iterable
        a, b = Picks(components=frozenset(), by_resource={})
```

**`test_smd_pick_all_sentinel_renamed`**

```python
def test_smd_pick_all_sentinel_renamed():
    from cloudinary_cli.modules.settings.engine.picks import SMD_PICK_ALL_SENTINEL
    assert SMD_PICK_ALL_SENTINEL == "__ALL_SMD__"
```

### 3.2 Streaming-profile built-ins

**`test_streaming_profiles_virgin_account_has_no_overridden_builtins`**
(integration; mocks the live `list_streaming_profiles` to return only
unmodified built-ins)

```python
def test_streaming_profiles_virgin_account_has_no_overridden_builtins(stub_api):
    stub_api.list_streaming_profiles.return_value = _virgin_builtins_response()
    bundle = export_streaming_profiles_bundle()
    assert bundle["overridden_builtins"] == []
    assert bundle["custom_profiles"] == []
```

**`test_streaming_profiles_overridden_builtin_is_captured`**

```python
def test_streaming_profiles_overridden_builtin_is_captured(stub_api):
    stub_api.list_streaming_profiles.return_value = _builtins_with_one_override("hd")
    bundle = export_streaming_profiles_bundle()
    assert [p["name"] for p in bundle["overridden_builtins"]] == ["hd"]
```

**`test_streaming_profiles_delete_builtin_requires_flag`**

```python
def test_streaming_profiles_delete_builtin_requires_flag(stub_api):
    res = runner.invoke(cli, ["settings", "streaming-profiles", "delete", "hd"])
    assert res.exit_code != 0
    assert "--allow-revert-builtins" in res.output
```

**`test_streaming_profiles_classification_failure_does_not_silent_delete`**

```python
def test_streaming_profiles_classification_failure_does_not_silent_delete(stub_api):
    stub_api.streaming_profile.side_effect = TransientError(503)
    res = runner.invoke(
        cli, ["settings", "streaming-profiles", "delete", "hd",
              "--allow-revert-builtins", "-F"],
    )
    assert res.exit_code != 0
```

### 3.3 Diff with picks restricts the deletion universe

**`test_diff_with_picks_restricts_delete_bucket`**

```python
def test_diff_with_picks_restricts_delete_bucket(stub_api):
    stub_api.upload_presets.return_value = _presets("p1", "p2", "p3")
    snapshot = _snapshot_with_presets("p1")
    plan = run_diff(snapshot, picks=[("upload_presets", "name", "p1")])
    assert plan.upload_presets.to_delete == []     # was ["p2", "p3"] before fix
    assert plan.upload_presets.to_update == []
    assert plan.upload_presets.to_create == []
```

### 3.4 `--cloud` on `restore` is the source namespace

**`test_restore_from_cloud_aliases_cloud_with_deprecation_warning`**

```python
def test_restore_from_cloud_aliases_cloud_with_deprecation_warning(stub_store, stub_api):
    res = runner.invoke(cli, ["settings", "restore", "foo", "--cloud", "demo"])
    assert "deprecated" in res.output.lower()
    stub_store.assert_loaded_from(cloud="demo", name="foo")
    stub_api.assert_applied_to(cloud=stub_api.ambient_cloud_name)
```

**`test_restore_from_cloud_explicit_flag_works`**

```python
def test_restore_from_cloud_explicit_flag_works(stub_store, stub_api):
    res = runner.invoke(cli, ["settings", "restore", "foo", "--from-cloud", "demo"])
    assert res.exit_code == 0
    assert "deprecated" not in res.output.lower()
```

### 3.5 Dirstore stale-file pruning

**`test_dirstore_save_prunes_stale_component_files`**

```python
def test_dirstore_save_prunes_stale_component_files(tmp_path):
    write_snapshot_dir(tmp_path, _snap(["smd", "transformations"]), ALL_RESOURCES)
    assert (tmp_path / "transformations.json").exists()
    write_snapshot_dir(tmp_path, _snap(["smd"]), ALL_RESOURCES)
    assert not (tmp_path / "transformations.json").exists()
    assert (tmp_path / "smd.json").exists()
    assert (tmp_path / "_index.json").exists()
```

**`test_dirstore_save_preserves_non_component_files`**

```python
def test_dirstore_save_preserves_non_component_files(tmp_path):
    (tmp_path / "README.md").write_text("kept")
    write_snapshot_dir(tmp_path, _snap(["smd"]), ALL_RESOURCES)
    assert (tmp_path / "README.md").read_text() == "kept"
```

### 3.6 Config warning is emitted exactly once

**`test_restore_with_config_emits_single_warning`**

```python
def test_restore_with_config_emits_single_warning(stub_store, stub_api, caplog):
    stub_store.put(_snapshot_with(["smd", "config"]))
    runner.invoke(cli, ["settings", "restore", "snap", "-F"])
    msgs = [r.message for r in caplog.records if "Config is captured" in r.message]
    assert len(msgs) == 1
```

**`test_apply_config_bundle_silent_no_op_returns_true`**

```python
def test_apply_config_bundle_silent_no_op_returns_true(caplog):
    caplog.set_level("WARNING")
    assert apply_config_bundle({"settings": {}}, target_options=None) is True
    assert not [r for r in caplog.records if "Config is captured" in r.message]
```

### 3.7 `--component` x `--pick` cross-validation

**`test_save_component_pick_mismatch_is_usage_error`**

```python
def test_save_component_pick_mismatch_is_usage_error():
    res = runner.invoke(cli, [
        "settings", "save",
        "--component", "smd",
        "--pick", "upload_presets", "name", "foo",
    ])
    assert res.exit_code != 0
    assert "upload_presets" in res.output
    assert "smd" in res.output
```

### 3.8 Empty-snapshot apply does not silently succeed

**`test_apply_to_target_empty_snapshot_returns_no_op_exit_code`**

```python
def test_apply_to_target_empty_snapshot_returns_no_op_exit_code(stub_store):
    stub_store.put({"schema_version": 1, "name": "snap", "components": []})
    res = runner.invoke(cli, ["settings", "restore", "snap", "-F"])
    assert res.exit_code == 2  # "nothing applied because nothing matched"
    assert "Nothing to apply" in res.output
```

### 3.9 Concurrency env var

**`test_engine_default_workers_reads_env_var`**

```python
def test_engine_default_workers_reads_env_var(monkeypatch):
    from cloudinary_cli.modules.settings.engine.workers import default_workers
    monkeypatch.setenv("CLOUDINARY_CLI_SETTINGS_WORKERS", "5")
    assert default_workers() == 5
    monkeypatch.delenv("CLOUDINARY_CLI_SETTINGS_WORKERS", raising=False)
    assert default_workers() == 30
    assert default_workers(override=2) == 2
    monkeypatch.setenv("CLOUDINARY_CLI_SETTINGS_WORKERS", "garbage")
    assert default_workers() == 30
```

---

## 4. Engine and resource-spec unit tests

These tests come online with [`settings-fix-plan.md`](settings-fix-plan.md)
Phase 2 and the [`settings-redesign.md`](settings-redesign.md) engine layer.

### 4.1 Executor

- `test_executor_runs_create_update_delete_buckets`
- `test_executor_swallows_already_exists_in_create_missing`
- `test_executor_does_not_swallow_already_exists_in_upsert`
- `test_executor_propagates_other_errors`
- `test_executor_returns_false_when_any_op_fails`
- `test_executor_dry_run_skips_all_calls`
- `test_executor_uses_default_workers_when_not_overridden`
- `test_executor_handles_empty_plan`
- `test_executor_retries_transient_once`

### 4.2 Errors classifier

- `test_classify_409_is_already_exists`
- `test_classify_message_already_exists`
- `test_classify_404_is_not_found`
- `test_classify_429_502_503_504_is_transient`
- `test_classify_403_is_read_only`
- `test_classify_unknown_is_fatal`
- `test_classify_handles_response_attribute`

### 4.3 Planner / diff helper

- `test_diff_create_only_when_target_empty`
- `test_diff_update_when_normalized_differs`
- `test_diff_delete_only_in_sync_mode`
- `test_diff_with_picks_restricts_delete_bucket` (== §3.3)
- `test_diff_with_picks_restricts_create_bucket`
- `test_diff_picks_wildcard_expansion`
- `test_diff_picks_collapse_on_all_sentinel`

### 4.4 Picks filter

- `test_picks_filter_returns_all_when_empty`
- `test_picks_filter_collapses_on_all_sentinel`
- `test_picks_filter_expands_wildcards`
- `test_picks_filter_unknown_pattern_yields_empty`

### 4.5 Reporter

- `test_render_plan_omits_zero_buckets`
- `test_render_plan_colorizes_diffs`
- `test_render_outcome_summary_counts`
- `test_render_plan_json_format`

### 4.6 ResourceSpec contract

- `test_every_registered_spec_defines_required_fields`
- `test_apply_order_respects_depends_on`
- `test_specs_with_applicable_false_have_no_create_update_delete`
- `test_specs_with_supports_delete_false_define_no_delete_fn`
- `test_streaming_profiles_spec_has_builtins_and_requires_explicit_revert`
- `test_transformations_spec_unsafe_update_true`

### 4.7 Per-resource normalization

- `test_upload_presets_normalize_strips_external_id_and_timestamps`
- `test_upload_presets_normalize_sorts_tags_and_allowed_formats`
- `test_transformations_normalize_strips_t_prefix`
- `test_streaming_profiles_normalize_collapses_representations_to_strings`
- `test_upload_mappings_normalize_keeps_only_folder_and_template`
- `test_smd_fields_normalize_drops_server_keys`
- `test_smd_rules_normalize_keeps_dependency_refs`

---

## 5. CLI tests

Each Click subcommand gets at least:

- A `--help` snapshot stored under `test/fixtures/settings/help/<command>.txt`.
- A happy-path invocation against stubbed `cloudinary.api.*`.
- An exit-code assertion matching the documented contract.

Subcommands:

- `cld settings save`
- `cld settings restore`
- `cld settings clone`
- `cld settings diff`
- `cld settings ls`
- `cld settings rm`
- `cld settings show`
- `cld settings folder`
- `cld settings components`
- `cld settings smd delete`
- `cld settings transformations delete`
- `cld settings upload-presets delete`
- `cld settings streaming-profiles delete`
- `cld settings upload-mappings delete`
- `cld settings config diff`

Plus a JSON-output schema assertion for any `--json` flag.

---

## 6. Live integration harness

### 6.1 Location and gating

- `test/integration/settings/`
- Skipped unless `CLOUDINARY_CLI_TEST_URL` is set.
- Each test wraps the run in `with using_test_account():` which
  `cloudinary.config(url=...)` from the env var.

### 6.2 Prefix-and-cleanup

- Every resource created during a test gets a UUID-prefixed identity:
  `_cli_it_<run_uuid>_<seq>_<name>`.
- Each test's `tearDown` issues unconditional deletes for everything created
  during the test, regardless of pass/fail. SMD's existing harness in
  [`test/test_modules/test_cli_settings.py`](../test/test_modules/test_cli_settings.py)
  is the model.

### 6.3 Per-resource round-trip

For each resource:

```python
def test_<resource>_save_restore_round_trip():
    seed_account_with_known_state()
    snapshot = save_to_temp_file()
    mutate_account()
    apply(snapshot, mode="sync")
    assert account_state_matches(snapshot)
```

For each resource also:

```python
def test_<resource>_clone_diff_sync_diff():
    seed_source_account()
    clone_to(target_account)
    assert diff(source, target).is_empty()
    mutate(target_account)
    apply_sync(source_snapshot, target_account)
    assert diff(source, target).is_empty()
```

Resources to cover (parity with SMD):

- `transformations`
- `upload_presets`
- `streaming_profiles` (custom only; built-ins via separate test using
  `--allow-revert-builtins`)
- `upload_mappings`
- `config` — read-only diff test only

### 6.4 Dependency-order tests

- Apply an `upload_presets` snapshot whose presets reference a named
  transformation; assert the transformation is created first.
- Apply an SMD snapshot containing rules that reference fields; assert the
  fields are created before rules.
- Sync-delete an SMD snapshot whose rules reference fields not in the
  snapshot; assert rules are deleted before fields.

### 6.5 Failure-mode tests

- API throws 429 mid-apply → engine retries once and succeeds.
- API throws 500 mid-apply → engine reports failure, does not roll back, leaves
  partial state (documented behavior).
- API throws 409 on create in `create-missing` mode → silent skip.
- API throws 409 on create in `upsert` mode → surfaces as failure.

---

## 7. CI strategy

| Suite | Trigger | Wall time budget | Required |
|---|---|---|---|
| Unit (engine + resources) | every PR | < 30 s | yes |
| CLI / snapshot / store | every PR | < 60 s | yes |
| Live integration | nightly + on-demand | < 15 min | required for releases |

- Live integration runs on a dedicated test product environment,
  `cloudinary-cli-it-<region>`. The credential lives in CI secrets only.
- Live integration is **also** runnable from a developer's machine via
  `make integration-test` after exporting `CLOUDINARY_CLI_TEST_URL`.
- The unit + CLI tiers must be deterministic (no networking). Mocks for
  `cloudinary.api.*` live in `test/_stubs/cloudinary_api.py`.

---

## 8. Tooling and conventions

- Test runner: `pytest`.
- Mock layer: `unittest.mock` for `cloudinary.api.*`. Anything below the SDK
  boundary must not be mocked individually; mock the SDK call.
- Golden fixtures: `test/fixtures/settings/<resource>/<case>.json`. One
  fixture per "interesting" account state, used by both unit and integration
  tests.
- Help-text snapshots: `test/fixtures/settings/help/<command>.txt`. Updated by
  running `pytest --update-help-fixtures`.
- Coverage gate (per file): branch ≥ 90 %; engine/snapshot ≥ 95 %.
- New tests must add fixtures under `test/fixtures/settings/`, not inline
  in the test file, when the JSON exceeds 20 lines.

---

## 9. Schedule

| Block | Tests added | Gates which fix-plan PR |
|---|---|---|
| A | §3.1 (v1/v2 collapse), §3.5 (dirstore prune), §3.6 (config warning) | PR 1, PR 5, PR 6 |
| B | §3.2 (streaming profiles), §3.3 (diff with picks), §3.4 (--cloud) | PR 2, PR 3, PR 4 |
| C | §4.1–§4.2 (executor + errors) | PR 7 |
| D | §4.3, §4.6, §4.7, §3.7, §3.8 | PR 8, PR 9, PR 10 |
| E | §3.9 (workers env var), §6 (integration parity) | PR 11, PR 13 |
| F | §6.4 (dependency order), §6.5 (failure modes) | nightly only |

A fix-plan PR is not mergeable until the tests in its row are green.

---

## 10. Out of scope

- Performance/load tests. The engine doesn't claim a throughput SLA.
- Fuzz testing of the snapshot envelope.
- Cross-version snapshot migration (the design rejects v2-style migration
  branches; see [`settings-fix-plan.md`](settings-fix-plan.md) Phase 0).
- Tests for deferred features (webhook triggers, Provisioning-API account
  config, SAML/users/groups).
