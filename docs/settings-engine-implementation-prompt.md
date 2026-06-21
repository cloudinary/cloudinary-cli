# Implementation prompt: settings engine

A self-contained prompt to hand to a separate coding agent (or a fresh chat
session) tasked with implementing the new internal architecture for
`cloudinary_cli/modules/settings/`.

> Copy everything from `## Prompt` below into the new agent's first message.
> The agent should not need any other context beyond what's in this file plus
> the repository.

---

## Prompt

You are implementing the new internal architecture for the `settings` module
of the `cloudinary-cli` repository. The user-facing CLI surface is the
contract; the entire layer below it is being rewritten to remove ~3,500 lines
of duplicated code, kill several hardcoded values, and make the module unit-
testable without `cloudinary.api.*` reachability.

### 1. Repository orientation

- Repo: `cloudinary-cli` (Python package, Click-based CLI).
- Branch to base from: `feature/settings`.
- Target package: `cloudinary_cli/modules/settings/`.
- Tests: `test/test_modules/test_cli_settings*.py` (unit / CLI), and a new
  `test/integration/settings/` that you will create for live-API tests gated
  on `CLOUDINARY_CLI_TEST_URL`.

### 2. Required reading (in this order, before writing any code)

1. `docs/settings.md` — end-user guide. **This is the contract.** Every
   command, flag, prompt, default, exit code, and stdout format described
   there must be unchanged after your work.
2. `docs/settings-redesign.md` — the architecture you are implementing. Treat
   §3 (Target architecture), §3.2 (`ResourceSpec` contract), §3.3 (engine),
   §6 (Snapshot format), and §7 (Migration plan) as normative.
3. `docs/settings-fix-plan.md` — the phased remediation plan. Phase 0 and the
   five Phase 1 fixes are prerequisites for the engine; Phase 2 is the engine
   migration itself. Implement in the PR order documented in §7 of that doc.
4. `docs/settings-test-plan.md` — the test matrix you must satisfy. Every
   regression test in §3 of that doc is mandatory.
5. `docs/settings-design.md` — current design (for context, not for behavior
   to preserve where it conflicts with `docs/settings-redesign.md`).
6. `docs/settings-implementation.md` — current implementation log. Useful for
   "why is this code shaped this way" questions; Phase 0–4 of the fix plan
   supersede the "Known stubs / TODOs" section.

If any of those files are missing or appear stale, stop and ask the user
before proceeding.

### 3. Hard constraints

Do not violate any of these without explicit user approval:

- **CLI surface is frozen.** `cld settings --help` and every subcommand's
  `--help` text must be byte-identical to the current branch unless one of
  the docs above explicitly schedules a change (e.g. `--cloud` →
  `--from-cloud` rename in fix plan §3.3).
- **Exit codes are part of the contract.** Empty-snapshot apply returns 2
  per fix plan §3.8; everything else preserves today's codes.
- **Snapshot envelope on disk** keeps every field except `lineage` and
  `serial` (per redesign §6). `schema_version` becomes `1`.
- **No new top-level dependencies** in `setup.py`/`requirements.txt`.
  Standard library plus what the repo already imports.
- **Provider-by-provider migration with parity harness.** Do not delete a
  legacy provider until the new resource spec has produced byte-identical
  plan output for the parity fixture. See §6.
- **One PR per migration step.** No mega-PR. Map each PR to the table in
  fix plan §7.
- **Public Python API for `cloudinary_cli.modules.settings.*` is private.**
  Anything outside `cloudinary_cli/modules/settings/cli/commands.py` and the
  Click group itself is internal. Do not export the engine types.
- **No comments narrating obvious code.** Comments only for non-obvious
  trade-offs, constraints, or invariants.

### 4. What you are building

A new layer under `cloudinary_cli/modules/settings/`:

```
cloudinary_cli/modules/settings/
├── __init__.py
├── cli/
│   └── commands.py
├── engine/
│   ├── __init__.py
│   ├── planner.py
│   ├── executor.py
│   ├── picks.py
│   ├── errors.py
│   ├── reporter.py
│   └── workers.py
├── resources/
│   ├── __init__.py
│   ├── _base.py
│   ├── smd_fields.py
│   ├── smd_rules.py
│   ├── transformations.py
│   ├── upload_presets.py
│   ├── streaming_profiles.py
│   ├── upload_mappings.py
│   └── config.py
├── snapshot/
│   ├── __init__.py
│   ├── envelope.py
│   ├── dirstore.py
│   └── store.py
└── registry.py
```

Use the exact contracts in `docs/settings-redesign.md` §3.2 (ResourceSpec),
§3.3 (Plan, execute, classify, render_plan), §3.4 (Picks). Do not invent
new shapes.

The current `providers/` directory and `commands.py` are **deleted at the
end** of the migration. Do not delete them earlier; the parity harness needs
them for comparison.

### 5. Order of work

Match `docs/settings-fix-plan.md` §7 exactly. The 14 PRs there are your
unit of work, in order.

For each PR:

1. Re-read the relevant fix-plan section (the PR row points to it).
2. Re-read the test rows that gate it (`docs/settings-test-plan.md` §9).
3. Implement the smallest change that makes those tests pass.
4. Run the full test suite locally; do not ship a red branch.
5. Update `CHANGELOG.md` only on the final PR (PR 14); intermediate PRs
   carry their own scope in the PR description.

Stop and ask the user before starting:

- PR 7 (engine extraction) — confirm the `Plan` and `ResourceOps` shapes
  with the user using a code sketch before writing the executor.
- PR 10 (SMD port) — confirm the `plan_extras=` hook for SMD datasource sync
  with the user before implementing.
- PR 12 (lineage/serial) — confirm the user wants them dropped vs preserved
  (redesign §6 recommends dropped; user must confirm).

### 6. Parity harness (required before deleting any legacy provider)

Add `test/test_modules/test_settings_parity.py`. For each resource:

1. Load a fixture from `test/fixtures/settings/<resource>/parity_input.json`
   that contains a realistic-shaped bundle (~10 items mixed across
   create/update/delete buckets).
2. Run the **legacy** provider's `apply_bundle(bundle, dry_run=True,
   force=True, mode="sync")` against a stubbed account and capture the plan
   output.
3. Run the **new** engine's `engine.execute(engine.diff(...), ...)` against
   the same stubbed account and capture the plan output.
4. Assert both outputs are byte-identical after stripping ANSI codes and
   trailing whitespace.
5. Assert the same identity sets land in to_create, to_update, to_delete.

The parity test for a resource must be green on `main` for at least one CI
run before the legacy provider file is deleted (final PR per resource).

### 7. Concurrency

One helper, `cloudinary_cli/modules/settings/engine/workers.py`:

```python
def default_workers(override: int | None = None) -> int:
    if override is not None:
        return max(1, override)
    raw = os.environ.get("CLOUDINARY_CLI_SETTINGS_WORKERS")
    if raw and raw.isdigit() and int(raw) >= 1:
        return int(raw)
    return 30
```

Every `ThreadPool(...)` site in the engine reads from this helper. Delete
all four `DEFAULT_WORKERS = 30` constants in `providers/*.py` once the
matching resource is ported.

### 8. Error classification

One classifier, `cloudinary_cli/modules/settings/engine/errors.py`. The
contract is in `docs/settings-redesign.md` §5. Replace the four
`_is_already_exists` copies. Map every SDK status code that the legacy
providers handle today; do not invent new behavior on `403` / `423` /
`429` / `502` / `503` / `504` until the user signs off (the redesign
proposes one bounded retry on transient errors; that is **opt-in** —
default off — until confirmed).

### 9. Snapshot envelope (Phase 0 prerequisite)

Implement Phase 0 of `docs/settings-fix-plan.md` first:

- `SCHEMA_VERSION = 1` in `snapshot/envelope.py`.
- `load_snapshot` raises `click.UsageError("This snapshot was written by
  an older or newer CLI: schema_version=<N>; expected 1.")` for any value
  other than `1`.
- `lineage` and `serial` fields are not written. `make_envelope` removes
  them from its return shape; `previous_serial_for_lineage` is deleted.
- `Picks` becomes `@dataclass(frozen=True, slots=True)`. No `__iter__`,
  no `__getitem__`. The one legacy 4-tuple unpack at
  `commands.py::smd_delete:250` becomes attribute access.
- `SMD_PICK_ALL_SENTINEL = "__ALL_SMD__"`. Update every reference.

If any of those changes break a test that wasn't on the list in fix plan
Phase 0 §3.1 acceptance criteria, stop and ask the user.

### 10. Testing requirements

- Unit (engine): ≥ 95 % branch coverage on `engine/*` and `snapshot/*`.
- Unit (resources): ≥ 90 % branch coverage on each `resources/*.py`.
- CLI tests: every Click subcommand has a `--help` snapshot under
  `test/fixtures/settings/help/<command>.txt` and a happy-path test.
- Every regression test in `docs/settings-test-plan.md` §3 exists with
  the exact test name shown there.
- Live integration tests under `test/integration/settings/` are
  env-var-gated on `CLOUDINARY_CLI_TEST_URL`. Skipping when unset must
  not affect PR pipeline status.
- Mocks live in `test/_stubs/cloudinary_api.py`. Do not mock below the
  SDK boundary.
- Run `pytest -x` after every commit. Do not push red.

### 11. Stop conditions

Stop and ask the user immediately if any of the following happen:

- A legacy provider's behavior is undocumented and the parity harness
  shows a divergence you can't explain from the design docs.
- A user-visible behavior change appears necessary that is not already
  scheduled in `docs/settings-fix-plan.md`.
- A test that you didn't expect to fail is failing and you can't trace
  it to your change in under 10 minutes.
- The parity harness produces non-deterministic output (e.g. dict
  ordering, timestamp drift). Fix the determinism, not the assertion.
- You discover a bug in the legacy code that affects users today and
  isn't already in the fix plan. File a separate issue; do not fold it
  into the migration.

### 12. Definition of done (whole engine, not per-PR)

- All 14 PRs from `docs/settings-fix-plan.md` §7 merged in order.
- `cloudinary_cli/modules/settings/providers/` does not exist.
- `cloudinary_cli/modules/settings/commands.py` does not exist (replaced
  by `cli/commands.py`).
- `cloudinary_cli/modules/settings/utils/` does not exist (replaced by
  `engine/` and `snapshot/`).
- Module LoC ≤ 3,500 (was 6,482). `wc -l
  cloudinary_cli/modules/settings/**/*.py` confirms.
- Live integration tier passes nightly with credentials.
- `cld settings save / restore / clone / diff / ls / rm / show / folder /
  components / smd delete / transformations delete / upload-presets
  delete / streaming-profiles delete / upload-mappings delete / config
  diff` all behave identically to current main except for changes
  documented in the fix plan.
- The "Known stubs / TODOs" section of
  `docs/settings-implementation.md` is empty (or that section is
  deleted entirely).
- `CHANGELOG.md` summarizes the engine migration under the next
  unreleased version.

### 13. First action when you start

Reply to the user with:

1. The PR list from `docs/settings-fix-plan.md` §7, confirming order.
2. Three explicit yes/no questions:
   a. Drop `lineage`/`serial` from the v1 envelope? (Recommended: yes.)
   b. Default `engine.errors` transient retry to **off**? (Recommended:
      yes — turn on later if SDK error semantics support it.)
   c. Should `cli/commands.py` keep accepting `--cloud` as a deprecated
      alias for `--from-cloud` for one release, or break it now?
      (Recommended: keep alias for one release.)

Wait for the user's answers before opening PR 1.

### 14. Things to **not** do

- Do not add new CLI commands or flags.
- Do not change the snapshot file format on disk beyond the lineage/serial
  removal.
- Do not introduce async, asyncio, anyio, trio, or any non-stdlib
  concurrency primitive. The engine uses `multiprocessing.pool.ThreadPool`,
  matching the legacy code.
- Do not introduce a new dependency (typing-extensions is already in the
  lockfile and is allowed if needed for `Protocol`/`Self`).
- Do not refactor unrelated modules. If you touch a file outside
  `cloudinary_cli/modules/settings/`, justify it in the PR description.
- Do not pre-emptively design for webhooks, Provisioning API, SAML, or
  cloud-backed storage. They are explicitly deferred per
  `docs/settings-design.md` §13.
- Do not write narrative comments. Code should be readable on its own.
- Do not delete or move the plan/fix/test/redesign markdown docs without
  user approval. Update them as the source of truth changes.

End of prompt.

---

## Notes for the prompt-giver (not for the implementing agent)

- Hand the implementing agent the entire `## Prompt` section above as the
  first message. They should reply with the §13 questions before
  touching code.
- If the agent skips the parity harness and proposes deleting legacy
  code outright, send them back to §6.
- If the agent proposes a CLI-level change ("we should add `--workers`"),
  remind them §3 is frozen.
- The agent's PR descriptions should include the row from
  `docs/settings-fix-plan.md` §7 they're implementing, so reviewers can
  trace each PR back to the plan.
- After PR 14 lands, the four planning docs
  (`settings-fix-plan.md`, `settings-redesign.md`, `settings-test-plan.md`,
  this prompt) become historical artifacts. Either archive them under
  `docs/history/` or delete; do not leave them as live design docs.
