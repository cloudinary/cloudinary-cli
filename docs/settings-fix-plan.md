# `cld settings` — Fix plan

A phased, time-ordered remediation plan for the `cloudinary_cli/modules/settings/`
module. Sequenced so each phase is mergeable on its own and so later phases build
on earlier ones.

> **See also:**
> - [`settings.md`](settings.md) — end-user guide for `cld settings`.
> - [`settings-design.md`](settings-design.md) — current technical design.
> - [`settings-implementation.md`](settings-implementation.md) — current
>   maintainer notes (what shipped, decisions, stubs).
> - [`settings-redesign.md`](settings-redesign.md) — proposed new architecture
>   that Phase 2 incrementally migrates to.
> - [`settings-test-plan.md`](settings-test-plan.md) — the test matrix and
>   regression list referenced by every phase's acceptance criteria.

Status: proposed.
Owner: feature/settings.
Scope: `cloudinary_cli/modules/settings/`.

---

## 0. Why this plan exists

The settings module is shipping for the first time. The review captured in
[`settings-redesign.md`](settings-redesign.md) found:

- v1-vs-v2 schema framing baked into code, tests, and docs even though there
  is no released v1. It's accidental complexity that doubles the surface area
  of `envelope.py`, `Picks`, and the SMD sentinel.
- One real, user-visible bug class (built-in streaming-profile detection,
  `--cloud` semantics on `restore`, `dirstore` stale-file leak, diff-with-picks
  delete bucket).
- Massive copy-paste across the four non-SMD providers (~1,800 LoC of code that
  is essentially the same loop with different SDK calls bound in).
- Hardcoded values (`DEFAULT_WORKERS = 30` x 4, `BUILTIN_STREAMING_PROFILE_DEFAULTS`,
  per-component log prefixes).
- Dead helpers (`format_plan_header`, `index_by` imports without callers,
  `SUPPORTED_COMPONENTS` alias).
- Patchy test coverage (SMD has live integration; the four newer providers don't).

This plan addresses the issues in the smallest mergeable units, leaves the
public CLI alone, and keeps the door open for the engine rewrite in
[`settings-redesign.md`](settings-redesign.md).

---

## 1. Plan at a glance

| Phase | Theme | Outcome | Public CLI | Snapshot format |
|---|---|---|---|---|
| 0 | Collapse v1/v2 | One released schema, no upgrade branch | unchanged | `schema_version: 1` |
| 1 | Bugs that block v1 | Correct behavior on all flows users will try | unchanged | unchanged |
| 2 | Refactor toward the engine | One `_apply_changes`, one error classifier, one diff dispatcher | unchanged | unchanged |
| 3 | Gaps | Concurrency knob, dir-mode lineage, integration parity | unchanged | unchanged |
| 4 | Docs and changelog | Docs tell the truth | unchanged | unchanged |

Phases 0, 1, and 4 are no-regret. Phase 2 is the largest in code volume but
introduces no user-visible change. Phase 3 is small.

---

## 2. Phase 0 — Collapse v1/v2

The `schema_version: 2` framing only exists because an SMD-only `schema_version: 1`
was prototyped and never released. Treat the current schema as v1 and delete
the soft-upgrade machinery.

### Scope

- Set `SCHEMA_VERSION = 1` in
  [`cloudinary_cli/modules/settings/utils/envelope.py`](../cloudinary_cli/modules/settings/utils/envelope.py)
  (line 37).
- Strip the upgrade branch in `load_snapshot` (lines 153–186): replace with a
  strict check that rejects any `schema_version` other than `1` with a clear
  `click.UsageError` ("This snapshot was written by an older or newer CLI:
  schema_version=<N>; expected 1.").
- Remove `previous_serial_for_lineage`'s tolerance for missing `schema_version`
  (no behavior change beyond Phase 0; it's just clearer).
- In [`cloudinary_cli/modules/settings/utils/pick.py`](../cloudinary_cli/modules/settings/utils/pick.py):
  - Replace the `Picks` class (lines 124–179) with a `dataclass(slots=True)`.
  - Drop `__iter__` and `__getitem__`.
  - Update the only legacy 4-tuple call site,
    [`cloudinary_cli/modules/settings/commands.py`](../cloudinary_cli/modules/settings/commands.py)::`smd_delete`
    line 250, to use named attributes.
  - Rename `SMD_PICK_ALL_SENTINEL` from `"__ALL__"` to `"__ALL_SMD__"`.
  - Remove the legacy-`__ALL__` fallbacks scattered in providers
    (`("*", "all", PICK_ALL_SENTINEL, "__ALL__")`).
  - Update the in-code references to the SMD sentinel
    ([`smd.py`](../cloudinary_cli/modules/settings/providers/smd.py) lines 70,
    72, 388, 390, 789, 791) to use the constant.
- Docs:
  - Strip the "Snapshot envelope (v2)" / "v1 backwards compatibility" subsection
    from [`docs/settings.md`](settings.md) and re-title to "Snapshot envelope".
  - Same treatment in [`docs/settings-design.md`](settings-design.md) §4.
  - Same in [`docs/settings-implementation.md`](settings-implementation.md)
    §4.1, §6.1, §7.
  - Update [`CHANGELOG.md`](../CHANGELOG.md) to drop the "v1 SMD-only snapshots
    remain loadable" line.
- Tests:
  - Delete `test_envelope_load_v1_snapshot_upgrades_in_memory` from
    [`test/test_modules/test_cli_settings.py`](../test/test_modules/test_cli_settings.py).
  - Add `test_envelope_load_rejects_unknown_schema_version`.
  - Update `test_picks_legacy_4_tuple_unpack` (rename to
    `test_picks_named_attributes`) — drop the `__iter__` assertion.
  - Update `test_envelope_v2_make_finalize_round_trip` to assert `schema_version == 1`.

### Acceptance criteria

- `grep -RIn "v1\|schema_version\s*==\s*\(2\|None\)" cloudinary_cli/modules/settings docs CHANGELOG.md` returns nothing.
- `cld settings save foo` writes `"schema_version": 1`.
- Passing a hand-rolled `{"schema_version": 0, ...}` snapshot to `cld settings restore --in` fails with the documented usage error.
- All existing tests pass; one new test is added; one is renamed.
- Test plan: covers items in [`settings-test-plan.md`](settings-test-plan.md) §3.1.

### Risk

- Low. The "v1 snapshot" file format never escaped into a release. Internal
  test fixtures referencing `schema_version: 1` are explicitly under our
  control.
- One risk: if a user already has a snapshot file on disk written from this
  branch (i.e. with `schema_version: 2`), Phase 0 makes it unloadable. That's
  acceptable because the branch is unreleased, but Phase 0 should mention this
  in the migration note inside the same PR's description (not in the docs,
  because users don't have v2 snapshots to migrate).

### Dependencies

- None. Phase 0 stands alone.

---

## 3. Phase 1 — Bugs that block v1

Five user-visible problems. Each can ship as its own commit; bundle into one PR
if convenient.

### 3.1 Built-in streaming-profile detection is misleading

**File:** [`cloudinary_cli/modules/settings/providers/streaming_profiles.py`](../cloudinary_cli/modules/settings/providers/streaming_profiles.py)
lines 64–86 (`BUILTIN_STREAMING_PROFILE_DEFAULTS`) and `_is_overridden_builtin`
(lines 129–142).

**Problem:** Every entry in the defaults table is `[{"transformation": "sp_auto"}]`
— a placeholder. The override-detection logic compares live `representations`
to this placeholder and almost always returns `True`, so saves capture
unmodified built-ins as "overridden_builtins". Diff output is noisy, and
`overridden_builtins` ends up containing entries that are not actually
customized.

**Fix:** Drop the static defaults table. Replace with:

```python
def _is_overridden_builtin(profile, *, defaults_lookup):
    """A built-in is "overridden" iff its current representations differ from
    the defaults reported by the API for that profile name."""
    if not isinstance(profile, dict) or not profile.get("predefined"):
        return False
    name = profile.get("name")
    defaults = defaults_lookup(name)
    if defaults is None:
        return True  # unknown built-in; conservative.
    return _normalize_representations(profile.get("representations")) != _normalize_representations(defaults)
```

`defaults_lookup` is a thin wrapper that fetches the named built-in from a
freshly-bootstrapped product environment baseline. For v1 we accept "fetched
from the same account", which is a small but acceptable approximation (a
brand-new account has its built-ins at server defaults; an account that has
overridden them will simply skip them, which is the correct behavior since the
user is the one who already knows the override exists).

If even that is too loose, a follow-up can add an opt-in
`--builtin-baseline=<account>` flag.

**Acceptance criteria:**

- On a virgin account (no overrides), `cld settings save --component streaming_profiles --out -` produces a bundle whose `overridden_builtins` list is empty.
- On an account with one overridden built-in, the bundle contains exactly that one entry.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §3.2.

### 3.2 `cld settings diff` with picks deletes the wrong universe

**File:** [`cloudinary_cli/modules/settings/commands.py`](../cloudinary_cli/modules/settings/commands.py)
`_run_diff` lines 657–706, plus each provider's `apply_*` planner.

**Problem:** `_run_diff` invokes `provider.apply_bundle(..., mode="sync",
dry_run=True, force=True)`. Each provider's planner computes the "delete"
bucket as `target_universe - source_universe`. When the user passes a `--pick`
that narrows the source (e.g. one specific upload preset), the source universe
shrinks but the target universe doesn't, so diff reports "would delete" for
every preset the user did not pick. That's not drift — it's a UX bug.

**Fix:** When picks are present, restrict the delete bucket to items in the
target whose identity matches the picks. Concretely, in each provider's
planner, change:

```python
to_delete = sorted(set(target_by_id) - set(source_by_id))
```

to

```python
delete_universe = (
    set(target_by_id) if not picks
    else expand_names_with_patterns(picks, set(target_by_id))
)
to_delete = sorted(delete_universe - set(source_by_id))
```

Cleanest way to reach all four planners: introduce a single
`engine.planner.diff(source_by_id, target_by_id, picks)` helper as part of
Phase 2 and call it from each provider. For Phase 1 we patch each provider in
place; Phase 2 deletes the duplication.

**Acceptance criteria:**

- `cld settings diff --pick upload_presets name p1` reports drift on `p1` only.
- `cld settings diff` with no picks behaves identically to today.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §3.3.

### 3.3 `--cloud` on `restore` is the source namespace, not the target

**File:** [`cloudinary_cli/modules/settings/commands.py`](../cloudinary_cli/modules/settings/commands.py)
lines 730–784.

**Problem:** `cld settings restore foo --cloud demo` reads the snapshot named
`foo` from the `demo` namespace under the local store, then applies it against
**ambient** `cloudinary.config()` — not against `demo`. Users who expect
`--cloud` to mean "apply to the demo product environment" silently target the
wrong account.

**Fix:** Decide and document. Keep the current behavior (it is consistent with
how `clone` separates `--from` from `targets`) but rename the option locally
in `restore`/`diff` to `--from-cloud`, accepting `--cloud` as a deprecated
alias for one release. Update help strings on both subcommands. Add an explicit
note in [`docs/settings.md`](settings.md) under "restore".

**Acceptance criteria:**

- `cld settings restore foo --from-cloud demo` reads from the `demo` namespace
  and applies to ambient.
- `cld settings restore foo --cloud demo` works with a deprecation warning.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §3.4.

### 3.4 `dirstore.write_snapshot_dir` leaks stale component files

**File:** [`cloudinary_cli/modules/settings/utils/dirstore.py`](../cloudinary_cli/modules/settings/utils/dirstore.py).

**Problem:** Saving with `--component smd --out-dir d/` writes `d/_index.json`
and `d/smd.json`. Saving again with `--component smd transformations --out-dir d/`
correctly adds `d/transformations.json`. Saving once more with `--component smd`
leaves `d/transformations.json` on disk; the next `read_snapshot_dir` merges
it back in. Saves are not idempotent on the directory.

**Fix:** Before writing, prune `<dir>/<component>.json` for any component **not**
in the current `components` list. Keep `_index.json`. Keep any non-component
files (don't touch `.git`, `README.md`, etc.).

**Acceptance criteria:**

- After a save with a narrower component set, `os.listdir(out_dir)` contains
  only `_index.json` and the JSON files for the current components, plus any
  non-`.json` files that were already there.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §3.5.

### 3.5 Config warning is emitted twice

**Files:** [`cloudinary_cli/modules/settings/commands.py`](../cloudinary_cli/modules/settings/commands.py)
`_apply_to_target` lines 922–928, and
[`cloudinary_cli/modules/settings/providers/config.py`](../cloudinary_cli/modules/settings/providers/config.py)
`apply_config_bundle` lines 87–94.

**Problem:** The orchestrator short-circuits `comp == "config"` before calling
`apply_bundle`, but the provider also emits the same warning if called
directly. Two emit sites, one message — they will drift.

**Fix:** Keep the orchestrator's warning. Make `apply_config_bundle` a silent
no-op that returns `True`. Document in
[`docs/settings-implementation.md`](settings-implementation.md) §4.16 that the
provider deliberately doesn't warn (the orchestrator owns the user-facing
message).

**Acceptance criteria:**

- `cld settings restore` with config in the snapshot emits exactly one warning
  line about config being read-only.
- A direct call to `apply_config_bundle(...)` in tests emits no warning and
  returns `True`.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §3.6.

---

## 4. Phase 2 — Refactor toward the engine

This is the largest change in code volume; **zero** user-visible change.
Sequenced so each step deletes more code than it adds. See
[`settings-redesign.md`](settings-redesign.md) for the target architecture.

### 4.1 One shared `_apply_changes` engine

**Files:**
- [`cloudinary_cli/modules/settings/providers/transformations.py`](../cloudinary_cli/modules/settings/providers/transformations.py) `_apply_changes` line 390.
- [`cloudinary_cli/modules/settings/providers/upload_presets.py`](../cloudinary_cli/modules/settings/providers/upload_presets.py) `_apply_changes` line 259.
- [`cloudinary_cli/modules/settings/providers/upload_mappings.py`](../cloudinary_cli/modules/settings/providers/upload_mappings.py) `_apply_changes` line 183.
- [`cloudinary_cli/modules/settings/providers/streaming_profiles.py`](../cloudinary_cli/modules/settings/providers/streaming_profiles.py) `_apply_changes` line 401.

**Problem:** Four near-identical implementations of "run create / update /
delete buckets through a `ThreadPool`, swallow `_is_already_exists` on
`create-missing`, log the per-resource prefix on every action."

**Fix:** New module `cloudinary_cli/modules/settings/engine/executor.py` with:

```python
def execute_plan(plan: Plan, *, ops: ResourceOps, mode: str, workers: int) -> bool: ...
```

`Plan` carries `to_create`, `to_update`, `to_delete`, plus an optional
`extras` for streaming profiles' built-in update bucket. `ResourceOps`
carries the four bound SDK callables and a `label` ("Upload presets"). Each
provider's `_apply_changes` becomes a 4-line call to `execute_plan`.

**Acceptance criteria:**

- The four `_apply_changes` functions are deleted.
- `engine/executor.py` is unit-tested without `cloudinary.api.*` reachability
  (callables mocked).
- Net delta: ≥ 200 LoC removed across providers; ≤ 80 LoC added in
  `engine/executor.py`.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §4.1.

### 4.2 One `_is_already_exists`

**Files:** Same four providers, lines 446 / 313 / 235 / 475.

**Problem:** Verbatim copies of the same six-line function.

**Fix:** Move to `cloudinary_cli/modules/settings/engine/errors.py` as
`is_already_exists(exc)`. Delete the four copies.

**Acceptance criteria:**

- `grep -RIn "_is_already_exists" cloudinary_cli/modules/settings/providers` returns nothing.
- Existing behavior preserved (status_code 409 OR substring match).
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §4.2.

### 4.3 Funnel `_apply_to_target` and `_run_diff` through the uniform contract

**File:** [`cloudinary_cli/modules/settings/commands.py`](../cloudinary_cli/modules/settings/commands.py)
lines 657–706 (`_run_diff`), 899–996 (`_apply_to_target`).

**Problem:** `_apply_to_target` re-implements per-component dispatch with an
`if/elif` ladder for SMD, transformations, upload_presets, streaming_profiles,
upload_mappings, even though every provider already exposes
`apply_bundle(bundle, *, target_options, picks, related, mode, dry_run, force)`.

**Fix:**

- Use `provider.apply_bundle(...)` in `_apply_to_target` for every component
  except `config`, just like `_run_diff` already does.
- Replace `_picks_for(component, parsed)` with a single dispatch table.
- `_run_diff`'s special-case for `config` becomes a flag on the provider
  (`provider.diffable_only = True`).

**Acceptance criteria:**

- `_apply_to_target` is < 40 LoC.
- The five if/elif branches are gone.
- All restore/clone tests still pass.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §4.3.

### 4.4 `--component` x `--pick` cross-validation

**File:** [`cloudinary_cli/modules/settings/utils/pick.py`](../cloudinary_cli/modules/settings/utils/pick.py).

**Problem:** `--component smd --pick upload_presets name foo` is silently
accepted; the upload_presets pick is dropped because the component isn't in
the selection. Users get an empty plan and no clue why.

**Fix:** In `parse_picks`, after parsing, if `selected_components` is non-empty
and contains components for which no picks were given, AND any of the picked
components are absent from `--component`, raise `click.UsageError` with the
specific mismatch.

**Acceptance criteria:**

- `cld settings save --component smd --pick upload_presets name foo` exits with
  a usage error that names both sides.
- `cld settings save --pick upload_presets name foo` (no `--component`) still
  works (picks-only selection).
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §4.4.

### 4.5 Delete dead code

- `SUPPORTED_COMPONENTS` alias in [`commands.py`](../cloudinary_cli/modules/settings/commands.py) line 79.
- `format_plan_header` in [`utils/render.py`](../cloudinary_cli/modules/settings/utils/render.py) line 207.
- `index_by` imports without callers in `transformations.py:22`,
  `streaming_profiles.py:41`, `upload_presets.py:21`. Either use them (replace
  inline `{p["name"]: p for p in items}` patterns) or drop them.
- `_normalize_for_compare` per-provider variants stay (they're the only
  per-resource difference) — but co-locate them in the resource spec rather
  than scattered through provider files.
- SMD's private `_format_section` / `_diff_any` / `_compact` /
  `_debug_log_diff` / `_index_by` / `_strip_dict_keys_deep`
  ([`smd.py`](../cloudinary_cli/modules/settings/providers/smd.py) lines 223,
  694, 762, 676, 848, 904) collapse onto the shared utils.

**Acceptance criteria:**

- `wc -l cloudinary_cli/modules/settings/**/*.py` is ≥ 600 LoC smaller than
  the pre-Phase-2 baseline (currently 6,482).
- No new public symbols.
- Test plan: [`settings-test-plan.md`](settings-test-plan.md) §4.5.

### Dependencies

- Phase 2 builds on Phase 1.5 (the diff-with-picks fix in §3.2 is the simplest
  pre-existing customer of the new planner helper).

---

## 5. Phase 3 — Gaps

### 5.1 `CLOUDINARY_CLI_SETTINGS_WORKERS` env var

- One helper in `cloudinary_cli/modules/settings/engine/executor.py`:

  ```python
  def default_workers(override=None):
      return override or int(os.environ.get("CLOUDINARY_CLI_SETTINGS_WORKERS", "30"))
  ```

- Delete the four `DEFAULT_WORKERS = 30` constants.
- Document under [`docs/settings.md`](settings.md) "Performance" subsection.

### 5.2 Lineage / serial in `--out-dir` mode

- If `lineage`/`serial` are kept (decision from
  [`settings-redesign.md`](settings-redesign.md) §"Snapshot format"), make
  `dirstore.write_snapshot_dir` read `<dir>/_index.json` first to inherit
  `lineage` and bump `serial`.
- If they are dropped, this section becomes "remove `lineage`/`serial` from
  the envelope" and is even smaller.

### 5.3 Live integration parity for the new providers

- Mirror SMD's `TestCLISettingsIntegration` for upload_presets,
  streaming_profiles, upload_mappings, transformations.
- Config gets a read-only diff test only.
- See [`settings-test-plan.md`](settings-test-plan.md) §6 for the harness.

---

## 6. Phase 4 — Docs and changelog

After Phases 0–3 land, the existing settings docs are out of date. Rewrite
the affected sections only:

- [`docs/settings.md`](settings.md): drop v2/v1 envelope sections; rename to
  "Snapshot envelope". Add the `--from-cloud` rename note. Add the
  `CLOUDINARY_CLI_SETTINGS_WORKERS` section.
- [`docs/settings-design.md`](settings-design.md): delete §4 paragraphs about
  v1/v2; rewrite §3 (architecture) to point at the new engine layout from
  [`settings-redesign.md`](settings-redesign.md).
- [`docs/settings-implementation.md`](settings-implementation.md): delete §4.1
  (legacy 4-tuple), §4.16 (config double-warning), §5.1 (placeholder defaults),
  §5.4 (concurrency knob), §5.6 (dir-mode lineage), §5.8 (`index_by` unused),
  §6.1 trailing legacy-helpers paragraph. Rewrite §1 module map to reflect
  the new layout.
- [`CHANGELOG.md`](../CHANGELOG.md): one entry summarizing Phases 0–3 under
  the next unreleased version.

---

## 7. Phase ordering and PR layout

Recommended PR layout:

| PR | Phase | Title | Notes |
|---|---|---|---|
| 1 | 0 | settings: collapse v1/v2 schema, rename SMD sentinel | Standalone |
| 2 | 1.1 | settings: drop placeholder built-in streaming-profile defaults | Behavior fix |
| 3 | 1.2 | settings: restrict diff delete bucket to picks | Behavior fix; extracts `engine/planner.diff` helper |
| 4 | 1.3 | settings: rename --cloud to --from-cloud on restore/diff | UX fix; deprecation alias |
| 5 | 1.4 | settings: prune stale component files in dirstore writes | Bug fix |
| 6 | 1.5 | settings: silence config provider apply warning | Bug fix |
| 7 | 2.1+2.2 | settings: extract engine/executor.py and engine/errors.py | Refactor; net -250 LoC |
| 8 | 2.3 | settings: route apply through uniform provider contract | Refactor; net -80 LoC |
| 9 | 2.4 | settings: validate --component vs --pick mismatches | Behavior fix |
| 10 | 2.5 | settings: delete dead helpers; collapse SMD onto shared utils | Refactor; net -200 LoC |
| 11 | 3.1 | settings: CLOUDINARY_CLI_SETTINGS_WORKERS env var | Feature |
| 12 | 3.2 | settings: dir-mode lineage/serial continuity (or removal) | Feature/cleanup |
| 13 | 3.3 | settings: live integration parity for new providers | Tests |
| 14 | 4 | settings: docs and changelog refresh | Docs only |

Each PR ships green against the test matrix in
[`settings-test-plan.md`](settings-test-plan.md).

---

## 8. Acceptance criteria for the whole plan

- All 14 PRs above have landed.
- `cld settings --help` is identical to today (Phase 1.3 aside).
- Snapshot files written by main are loadable by main; cross-version load is
  rejected with a clear error.
- Module LoC is ≥ 1,000 lines smaller than the pre-plan baseline (current:
  6,482).
- Live integration tests run nightly with credentials and pass.
- The `Known stubs / TODOs` section in
  [`docs/settings-implementation.md`](settings-implementation.md) is empty.

## 9. Out of scope for this plan

Tracked separately because they have their own design surface:

- Webhook triggers (composite identity; design needed).
- Provisioning-API account-config writes (separate auth surface).
- SAML / users / groups / access-control rules / eval add-ons.
- Cloud-backed snapshot storage (the original motivation for `lineage`/`serial`;
  if it never materializes, those fields go away in Phase 3.2).
