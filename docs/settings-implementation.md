# `cld settings` — Implementation notes

A maintainer-oriented log of decisions made while implementing the design at
`[docs/settings-design.md](settings-design.md)`. Read this **after** the
design doc and `[docs/settings.md](settings.md)` (user guide). It records:

- which design choices were realized faithfully,
- which were extended or relaxed (and why),
- choices the design didn't specify that ended up in the code,
- known stubs / TODOs that warrant attention before the next release,
- testing gotchas, and
- a runbook for adding a new provider.

Status: complete, all 22 unit tests green.

---

## 1. Module map

```
cloudinary_cli/modules/settings/
├── commands.py                  CLI surface (Click). Composes providers,
│                                snapshot envelope, and the local store.
├── store.py                     Local store: paths, listing, ensure-dirs,
│                                cloud_name resolution. (No business logic.)
├── providers/
│   ├── __init__.py              Provider registry: PROVIDERS, APPLY_ORDER,
│   │                            ALL_COMPONENTS, DEFAULT_COMPONENTS,
│   │                            get_provider(), supports_delete(),
│   │                            list_components_status().
│   ├── smd.py                   SMD fields + rules; pre-existing, wrapped
│   │                            with the uniform contract; rules-aware
│   │                            datasource sync.
│   ├── smd_table.py             (pre-existing) tabular renderer for SMD.
│   ├── transformations.py       Named transformations.
│   ├── upload_presets.py        Upload presets (signed/unsigned).
│   ├── streaming_profiles.py    Custom + overridden built-in profiles.
│   ├── upload_mappings.py       Auto-upload mappings.
│   └── config.py                Product environment config (read/diff only).
└── utils/
    ├── render.py                Shared CLI rendering: c() (color), section /
    │                            item formatters, diff_any, compact, line
    │                            colorizer.
    ├── normalize.py             Generic helpers: strip_dict_keys_deep,
    │                            sort_string_list_value, is_pattern,
    │                            expand_names_with_patterns, index_by.
    ├── pick.py                  --pick parsing → Picks dataclass; legacy
    │                            4-tuple unpacking preserved via __iter__.
    ├── envelope.py              v2 envelope construction, fingerprints,
    │                            checksum, v1 soft-upgrade loader,
    │                            previous_serial_for_lineage().
    └── dirstore.py              --out-dir / --in-dir reader/writer
                                  (`_index.json` + `<comp>.json`).
```

The split mirrors the layered diagram in design §3:
**CLI ← Provider ← Store / SDK**, with `utils/` as cross-cutting helpers.

---

## 2. Design alignment matrix

A quick "what's faithful, what's not" cross-reference.


| Design § | Item                                                  | Status      | Notes                                                                                                                        |
| -------- | ----------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 2        | Six components in scope                               | as designed | smd, transformations, upload_presets, streaming_profiles, upload_mappings, config                                            |
| 3.1      | Provider contract (signatures + module attrs)         | as designed | `COMPONENT`, `PICK_KINDS`, `PICK_ALL_SENTINEL`, `export_bundle`, `summarize_bundle`, `apply_bundle`, optional `delete_items` |
| 3.2      | Apply mode semantics                                  | as designed | `create-missing` / `upsert` / `sync` truth table held in each provider                                                       |
| 3.3      | `--pick <group> <kind> <value>` + wildcards           | as designed | per-component sentinels; `*`/`all` keyword aliases                                                                           |
| 3.4      | Apply ordering                                        | as designed | `APPLY_ORDER` tuple in `providers/__init__.py`                                                                               |
| 4        | v2 envelope                                           | as designed | `lineage`, `serial`, `writer`, `source`, `selection`, `metadata`, `fingerprints`, `checksum`                                 |
| 4 v1 BC  | v1 snapshots load unchanged                           | as designed | soft-upgrade in-memory; never mutates the file on disk                                                                       |
| 4.1      | Directory mode `--out-dir` / `--in-dir`               | as designed | `_index.json` + `<component>.json`                                                                                           |
| 5        | CLI surface                                           | as designed | every subcommand listed                                                                                                      |
| 5        | `cld settings components`                             | as designed | new subcommand, gcloud-style                                                                                                 |
| 6.1      | SMD identity, datasource sync, rule blocking          | as designed | inherited from prior implementation                                                                                          |
| 6.2      | Transformations parity                                | as designed | rewritten to match SMD plan/normalize/error patterns                                                                         |
| 6.3      | Upload presets                                        | as designed | `unsigned` mutability respected; `external_id`/timestamps stripped                                                           |
| 6.4      | Streaming profiles split (custom + overridden)        | as designed | with one **stub** in the defaults table (see §5 below)                                                                       |
| 6.4      | Built-in delete refusal w/o `--allow-revert-builtins` | as designed | refuses with `logger.error`, returns `False`                                                                                 |
| 6.5      | Upload mappings                                       | as designed | identity = `folder`                                                                                                          |
| 6.6      | Config: capture always, never auto-apply              | as designed | warning emitted at apply time                                                                                                |
| 7        | Per-component success aggregation                     | as designed | `_apply_to_target` returns `bool`                                                                                            |
| 8        | Concurrency: `ThreadPool(30)`                         | as designed | per-provider; not yet env-tunable                                                                                            |
| 9        | Unit tests for parsers, providers, envelope           | as designed | 22 tests; live integration tests pre-existing for SMD only                                                                   |
| 12       | Decisions list                                        | as designed | per-component confirms; no symbolic link rewriting                                                                           |


---

## 3. Decisions made faithful to the design

These are worth restating because they constrain future work.

### Provider contract is enforced by convention, not by ABC

Each provider exposes top-level functions/constants matching the design's
signatures (no base class, no Protocol). Pros: easy to grep, easy to add a
provider, no MRO complexity. Cons: no `mypy --strict` shape verification —
relies on the registry tests in
`test_provider_registry_shape` to catch missing attrs/functions.

> If we ever add stricter typing, `typing.Protocol` is the right shape — keep
> the existing module-level functions and just declare the protocol.

### `APPLY_ORDER` tuple is the single source of truth for ordering

```python
APPLY_ORDER = (
    "upload_mappings",
    "streaming_profiles",
    "transformations",
    "smd",          # fields-then-rules is internal to the SMD provider
    "upload_presets",
    "config",
)
```

`_apply_to_target` in `commands.py` always iterates this tuple,
intersecting with the user's `--component` selection. Re-ordering for
`delete` is the SMD provider's responsibility (rules-before-fields).

If you add a component, append it to `APPLY_ORDER` *and* to `PROVIDERS` in
the same commit; otherwise it'll be in one but not the other and saves
will silently skip it.

### Per-component "all" sentinels (not a single `__ALL__`)

```
SMD_PICK_ALL_SENTINEL                  = "__ALL__"               # legacy, kept for v1 compat
TRANSFORMATIONS_PICK_ALL_SENTINEL      = "__ALL_TRANSFORMATIONS__"
UPLOAD_PRESETS_PICK_ALL_SENTINEL       = "__ALL_UPLOAD_PRESETS__"
STREAMING_PROFILES_PICK_ALL_SENTINEL   = "__ALL_STREAMING_PROFILES__"
UPLOAD_MAPPINGS_PICK_ALL_SENTINEL      = "__ALL_UPLOAD_MAPPINGS__"
```

Per-component sentinels mean a provider's `_filter_list(items, picks)` can
disambiguate "all of *my* component" from "all of some other component" if
sentinels ever cross provider boundaries — they shouldn't, but the
extra-explicit form costs nothing.

The legacy `__ALL__` (used by SMD long before this rework) is still
accepted everywhere via the `("*", "all", PICK_ALL_SENTINEL, "__ALL__")`
match list inside each provider's `_filter_list`.

### Pretty-JSON snapshots (`indent=2`)

Both single-file and per-component-directory writers pass `indent=2`. This
is on purpose: snapshots are diff-friendly text artifacts, not hot-path
data. Don't switch to compact JSON to "save bytes" — the size is
negligible and the diffability is the whole point.

---

## 4. Decisions that diverge from or extend the design

These are the parts a future maintainer is most likely to need to know.

### 4.1 `Picks` class with legacy 4-tuple `__iter__` for back-compat

The pre-existing `parse_picks` returned exactly:

```python
(selected_components, smd_fields, smd_rules, transformation_names)
```

…and SMD/transformations callers unpacked it directly. Adding three new
components without breaking those callers led to a small wrapper class:

```python
class Picks:
    __slots__ = (
        "selected_components",
        "smd_fields", "smd_rules", "transformation_names",
        "upload_preset_names", "streaming_profile_names",
        "upload_mapping_folders",
    )
    def __iter__(self):
        # Legacy 4-tuple unpacking order.
        yield self.selected_components
        yield self.smd_fields
        yield self.smd_rules
        yield self.transformation_names
```

Old callers that do `_, smd_fields, smd_rules, _ = parse_picks(picks)` keep
working unchanged; new callers use `parsed.upload_preset_names` etc. or
`parsed.for_component(<key>)`.

> If we ever drop the legacy unpacking, replace the class with a
> `dataclass(slots=True)` and remove `__iter__`/`__getitem__`.

### 4.2 `commands.py` imports providers' top-level names directly

```python
from .providers.smd import (
    apply_smd_bundle, delete_smd_items, export_smd_bundle,
    summarize_smd_bundle, render_smd_fields_table,
)
```

This means tests must patch the *imported* name in the `commands` module,
not the originating provider, when testing CLI flow:

```python
patch.object(settings_commands, "diff_config_bundle", return_value=True)
# NOT:  patch.object(cfg_provider, "diff_config_bundle", ...)
```

The test `test_settings_diff_invokes_apply_dry_run_for_components` enforces
this; if you ever switch to `from . import providers` style, that test
becomes obsolete and you can patch on the provider itself.

### 4.3 `apply_bundle` for `config` returns `True` (success), not `False`

Design says "always skip with a warning." A naive interpretation would be
to fail the call (return `False`). We chose to **return `True`** so a
multi-component restore that includes `config` doesn't get a non-zero
overall exit code purely from the deliberate-no-op. The user-facing signal
is the warning line.

```python
def apply_config_bundle(bundle, target_options=None, **_):
    logger.warning(
        "Config is captured for diffing only and is never applied. "
        "Use `cld settings diff --component config` to see drift; change "
        "values in the Console or via the Provisioning API."
    )
    return True
```

`commands.py::_apply_to_target` short-circuits `comp == "config"` *before*
calling the provider so the warning comes from the orchestrator, but the
provider's own `apply_bundle` is still safe to call directly (the test
suite does).

### 4.4 `cld settings diff` reuses providers' `apply_bundle(mode=sync, dry_run=True, force=True)`

The design promotes "drift" to a first-class verb without specifying a
separate diff renderer. We piggy-back on each provider's existing
planner: invoking `apply_bundle` in `mode=sync, dry_run=True, force=True`
emits the full create/update/delete plan without any side effects, then
the CLI converts the boolean return into a drift counter.

```python
result = provider.apply_bundle(
    bundle,
    target_options=None,
    picks=_picks_for(comp, parsed),
    related=None,
    mode="sync",       # exposes all three buckets
    dry_run=True,
    force=True,        # bypass the interactive confirmation
)
```

Implications:

- `force=True` is **deliberate** even though the user didn't pass `-F`.
Diff never writes; the prompt would just be friction.
- `mode="sync"` is **deliberate** because only `sync` shows the
"delete from target" bucket. If you change this to `upsert`, drift in
the deletion direction will silently disappear.
- Output is the same plan format as a real apply — pro: consistency, con:
it's not a custom Git-style diff. If you want a more compact diff
format later, do it inside each provider's plan output (so apply gets
the same upgrade for free).
- For `config`, we *don't* go through `apply_bundle`; we call
`diff_config_bundle` directly because the apply is a no-op.

### 4.5 `cld settings save` interactive default name

Design specifies `cld settings save [NAME]`. We added a TTY-only prompt
that suggests a sensible default when `NAME` is omitted:

```python
default_name = f"{cloud_name}_{components_label}_{YYYY-MM-DD_HH-MM-SS-mmm}"
```

In CI / non-TTY contexts, the prompt is skipped and the default is used
directly. `-F` also skips the prompt.

`<components_label>` is `"all"` when every supported component was
selected, otherwise dash-joined component keys (e.g.
`smd-upload_presets`).

### 4.6 `serial` only auto-bumps for store entries

```python
target_path = None
if not (out_file or out_dir):
    target_path = get_settings_store_snapshot_path(cloud_name, name)
prev_lineage, prev_serial = previous_serial_for_lineage(target_path)
```

For `--out`/`--out-dir`, we treat each save as a fresh `lineage`/`serial`.
The reasoning:

- A user who hands you a `bundle.json` doesn't have a guaranteed-stable
on-disk identity for that file (might be in a checkout, a tmpdir, etc.);
inheriting serial across `git checkout`s would be misleading.
- The store path is namespaced by `<cloud>/<name>`, so identity is
meaningful there.

If you decide to honor lineage for `--out`/`--out-dir` later, read the
existing file first and pass its `lineage`/`serial+1` to `make_envelope`.

### 4.7 `clone` accepts saved-config name **or** `cloudinary://…` URL

```python
target_config = get_cloudinary_config(target)   # name OR URL
target_options = config_to_dict(target_config)
target_cloud   = target_options.get("cloud_name", target)
```

This is a small UX extension over the design's "TARGET" abstraction.
`get_cloudinary_config` is the same helper the rest of the CLI uses, so
behavior matches `cld config` semantics.

### 4.8 `settings diff` and `settings config diff` have non-zero exit on drift

`_run_diff` returns `True` only when `drift_count == 0`. Click maps
`False` returns to non-zero exit codes via the wider CLI machinery — so
this is a usable CI guard out of the box.

```bash
cld settings diff prod-baseline || alert "drift detected"
```

The design mentions drift visibility but didn't specify exit codes; this
choice makes the guard pattern work without extra plumbing.

### 4.9 `ls --json` and `ls --tag` enrich entries by reading every snapshot

Plain `ls` is fast (filesystem listing only). Adding `--json` or `--tag`
reads every snapshot file to enrich the row with `lineage`, `serial`,
`tags`, `notes`, etc. For large stores this is O(n) file reads on every
call. If that ever becomes painful, the right fix is a sidecar index file
per cloud (`~/.cloudinary-cli/settings/<cloud>/_index.json`) — but it's
not justified yet.

### 4.10 `delete_streaming_profiles(allow_revert_builtins=False)` is the one provider with an extra kwarg

The uniform contract specifies `delete_items(target_options, picks, related, dry_run, force)`. Streaming profiles add `allow_revert_builtins` because
the design's "default refusal" needs an explicit opt-in flag.

`commands.py`'s `streaming_profiles_delete` is the only caller that wires
this through; `_apply_to_target` doesn't surface it (which is correct —
restore/clone never delete built-ins).

If you add another provider with a similar opt-in flag, prefer wiring it
through `delete_items` directly rather than introducing a new top-level
kwarg in the CLI orchestrator.

### 4.11 `force=True` semantics are split between "skip prompt" and "overwrite file"

- In providers' `apply_bundle`, `force=True` skips the
`"Continue? (y/N)"` prompt before applying.
- In `save`, `-F`/`force` additionally skips the
`"already exists. Overwrite?"` prompt.

These overlap but aren't identical. Don't fold them into one — that
breaks "I want to overwrite the file but still want a sanity prompt
before mutating Cloudinary".

### 4.12 Snapshot canonical-JSON for fingerprints/checksum uses `ensure_ascii=False`

```python
def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

`ensure_ascii=False` is deliberate: non-ASCII labels (Hebrew, CJK, …)
serialize as themselves, not as `\uXXXX` escapes. This makes a
fingerprint stable even if the SDK ever changes how it returns Unicode.
The trade-off: the bytes-on-the-wire of the canonical form become
UTF-8 — which is exactly what `hashlib.sha256(text.encode("utf-8"))`
hashes, so no correctness issue.

If you change this flag, every existing snapshot's checksum becomes
invalid even if its content is byte-identical. Don't.

### 4.13 `transformation_string` import has a runtime fallback

```python
try:
    from cloudinary.api import transformation_string
except ImportError:
    transformation_string = None
```

The SDK re-exports `transformation_string` through `cloudinary.api`, but
older releases either name it differently or only expose it as a private
helper. We resolve at import time, fall back to `None`, and the
representation normalizer in `streaming_profiles.py` falls back to a
stable `json.dumps(..., sort_keys=True)` string when `None`. The fallback
form *is* deterministic, so the override-detection logic still works —
you'll just see a JSON-shaped string rather than a transformation string
for edge-case representations.

> If the SDK floor is ever raised to a version that always exports it,
> drop the try/except and the `if transformation_string is not None`
> branches.

### 4.14 Pick "groups" are component keys; "kinds" are intra-component identifiers

The grammar `--pick <group> <kind> <value>` is uniform, but kinds are
component-specific: `field`/`rule` for SMD, `name` for transformations /
upload_presets / streaming_profiles, `folder` for upload_mappings. This is
exactly what the design says; what's worth recording is that the
validation lives in `pick.py`, *not* in the providers — i.e., a
provider can assume any pick it receives is valid for its kinds. If you
add a kind, edit `pick.py` and the matching `Picks` slot together.

### 4.15 SMD provider has a `_split_picks` shim because of its dual kinds

SMD is the only component with two kinds (`field`, `rule`). Its
`apply_bundle`/`delete_items` accept `picks` as a `(fields, rules)`
2-tuple while all others accept a flat list. `_picks_for(component, parsed)` in `commands.py` does the per-component translation — that's
where to look if a pick isn't reaching the provider correctly.

### 4.16 `config` apply never reaches the provider in the orchestrator

`_apply_to_target` short-circuits `comp == "config"` before calling
`apply_bundle`. The provider's `apply_bundle` (which prints the same
warning and returns `True`) is still kept in the file because:

1. it satisfies the uniform contract (registry tests would fail without it),
2. third-party callers (or future code paths like a `dry-run validate`)
  that iterate `PROVIDERS` directly will get a clean no-op without a
   special case.

---

## 5. Known stubs / TODOs

These are the items most likely to require follow-up. Prioritized.

### 5.1 `BUILTIN_STREAMING_PROFILE_DEFAULTS` is a placeholder

```python
BUILTIN_STREAMING_PROFILE_DEFAULTS = {
    "4k":            [{"transformation": "sp_auto"}],
    "full_hd":       [{"transformation": "sp_auto"}],
    "hd":            [{"transformation": "sp_auto"}],
    "sd":            [{"transformation": "sp_auto"}],
    "full_hd_wifi":  [{"transformation": "sp_auto"}],
    "full_hd_lean":  [{"transformation": "sp_auto"}],
    "hd_lean":       [{"transformation": "sp_auto"}],
}
```

Every entry uses the same `sp_auto` placeholder. The design (§6.4)
specifies that this table should be **seeded from the actual published
defaults** so the override-detection logic correctly identifies which
built-ins are overridden vs unchanged.

**Risk:** as written, almost any built-in will be classified as
"overridden" because the live `representations` won't match `sp_auto`.
That means saves capture more than they need to. Apply is still safe
(built-ins are never created/deleted from `restore`/`clone`; only
`update` is issued, which simply re-applies the captured override —
which equals whatever the live representations were at save time, so
nothing breaks in practice).

**Action:** before promoting this feature past beta, run:

```bash
# On a virgin product environment, fetch every built-in's representations
# and replace the values in the table.
for name in 4k full_hd hd sd full_hd_wifi full_hd_lean hd_lean; do
  cld admin get_streaming_profile $name | jq '.data.representations'
done
```

The design also calls for a unit test that compares the table against a
live fetch on a virgin account — write that test once the table is
seeded.

### 5.2 No `cld admin trigger…` integration (deferred — design §13.2)

Webhook triggers aren't a v1 component. Don't add one piecemeal — the
design has a sketch and there's a known footgun around composite
identity (`(event_type, uri)`).

### 5.3 No `--account-config` apply for `config` (deferred — design §13.3)

Provisioning API support is its own auth surface. The current code path
is structured to accept this without schema changes: just add a write
function in `providers/config.py` and a CLI flag.

### 5.4 No env-tunable concurrency knob

Design §8 mentions making workers configurable via
`CLOUDINARY_CLI_SETTINGS_WORKERS`. We hard-coded `DEFAULT_WORKERS = 30`
per provider. Easy follow-up — a single helper in `defaults.py` or
`providers/__init__.py` and pass through to each `apply_*`/`export_*`.

### 5.5 No live integration tests for new providers

`TestCLISettingsIntegration` covers the SMD round-trip only. Mirror
tests for upload_presets / streaming_profiles / upload_mappings would
follow the same prefix-and-cleanup pattern. They'll need to be gated on
real credentials and either skipped or guarded against accidental writes
to a non-test environment.

### 5.6 `previous_serial_for_lineage` only inspects single-file store entries

For `--out-dir` snapshots there's no equivalent "what's the previous
serial" lookup. `make_envelope(serial=1)` is always passed, so re-saving
to the same dir resets serial to 1. Acceptable today (Git is the
versioning layer for dir mode), but if you ever want intra-dir lineage
continuity, read `<dir>/_index.json` first and use its
`lineage`/`serial+1`.

### 5.7 `_representation_to_string` JSON fallback may produce non-canonical strings

When `cloudinary.api.transformation_string` is unavailable, the fallback
serializes the rep dict via `json.dumps(..., sort_keys=True)` — a stable
string but not a Cloudinary transformation string. That's safe for
*comparison* (we only compare to other captured strings), but if anyone
ever writes the captured string back through a code path that expects a
transformation string, they'll get the JSON literal instead.

The current code path doesn't do that (apply uses
`_representations_for_apply`, which wraps strings as
`{"transformation": <str>}`), so this is dormant. Worth a comment if you
add a new code path that consumes representations.

### 5.8 `index_by` in `utils/normalize.py` is currently unused

It's imported by upload_presets and streaming_profiles for future use;
neither calls it yet. Either delete the imports or use it where the
providers currently inline the dict comprehension `{p["name"]: p for …}`.
Preference: keep the helper, refactor providers to use it for
consistency in a follow-up.

---

## 6. Per-component implementation notes

### 6.1 `smd`

- Pre-existing implementation; this rework only **wrapped it** with the
uniform contract via top-of-file:
  ```python
  COMPONENT = "smd"
  PICK_KINDS = ("field", "rule")
  PICK_ALL_SENTINEL = "__ALL__"
  ```
  and helpers `export_bundle` / `summarize_bundle` / `apply_bundle` /
  `delete_items` that delegate to the legacy
  `export_smd_bundle` / … functions.
- The legacy `_split_picks` is the only place where picks are decoded
back into the dual `(fields, rules)` shape.
- Rendering helpers in `smd_table.py` are only used here; we left them
in place rather than moving to `utils/render.py` to keep the diff
minimal.

### 6.2 `transformations`

- Rewritten to mirror SMD parity (plan output, normalization,
error handling). The previous version did a bare `logger.info` plan
without colorization and swallowed all `409`s; it now uses
`render.format_section` / `format_updates_with_diffs` and limits
`409` swallowing to the `create-missing` mode via `_is_already_exists`.
- `t_*` prefix handling: list/get returns `t_<name>`; create/update/delete
expect bare names. Stripping happens in `_strip_named_prefix`.
- `unsafe_update=True` is set on update calls so renaming chains works
even when other transformations reference them.

### 6.3 `upload_presets`

- `_FORBIDDEN_TOP_LEVEL = {"external_id", "created_at", "updated_at"}`
mirrors the design's "noisy keys".
- `_LIST_LIKE_KEYS = ("tags", "allowed_formats")` are sorted **for
comparison only**; the original (unsorted) value is what apply sends
back, so we don't change semantics for ordering-sensitive consumers.
- `_serialize_preset` projects the SDK detail to
`{name, unsigned, settings}` — the only fields that round-trip.

### 6.4 `streaming_profiles`

- Bundle shape is two lists: `custom_profiles` and
`overridden_builtins`. Saves only include built-ins whose
representations differ from the (placeholder) defaults table — see
§5.1 above.
- Apply has two distinct planners (`_plan_custom`, `_plan_builtins`).
Built-ins always go through `update` only; never `create`, never
`delete`-from-`sync`.
- Standalone delete refuses built-ins by default with a clear error
*and a non-zero return*, so `cld settings streaming-profiles delete sd`
is a hard-stop until the user re-runs with `--allow-revert-builtins`.
- `_representations_for_apply` reverses the normalization: list of
strings → list of `{"transformation": <str>}`.
- See §4.13 above on the `transformation_string` import.

### 6.5 `upload_mappings`

- Identity = `folder`; only `template` is mutable.
- `_normalize_mapping` projects to `{folder, template}` — drops
`external_id`, timestamps.
- The list endpoint paginates with `call_api_with_pagination`.

### 6.6 `config`

- `apply_bundle` returns `True` (success no-op); see §4.3.
- `export_config_bundle` survives a failed `cloudinary.api.config(…)`
by returning `{"settings": {}, "applicable": False}` rather than
failing the whole save.
- `_project_config` projects to `{cloud_name, created_at, settings}`
to keep the bundle small and forensically meaningful.
- `diff_config_bundle` returns `False` on drift (so the wider
`cld settings diff` exit code is non-zero) and `True` on no drift.

---

## 7. Cross-cutting implementation choices

### 7.1 Concurrency

- Each provider uses `multiprocessing.pool.ThreadPool(N)` with
`N = min(DEFAULT_WORKERS=30, len(items))`.
- Reads parallelize where the SDK has a per-item detail endpoint
(`upload_preset(name)`, `get_streaming_profile(name)`).
- Writes parallelize within a phase (creates parallel, then updates
parallel, then deletes parallel) but phases run serially. This
keeps human-readable ordered logs and avoids one-failure-masks-others.

### 7.2 Pagination

All list endpoints go through `cloudinary_cli.utils.api_utils .call_api_with_pagination(func, kwargs=None, force=False)`. We always
pass `force=True` because settings exports are infrequent and total
dataset sizes are small.

### 7.3 Error model

- Provider apply functions return `bool`. `False` aggregates to non-zero
exit at the CLI level via `_apply_to_target` returning the AND of all
components.
- Per-item exceptions in `ThreadPool.map` are caught inside the worker
function (`_create`, `_update`, `_delete`) so a single failure
doesn't kill the whole map.
- `_is_already_exists(exc)` is a tiny helper used by every provider
that supports `create-missing`. It checks `status_code == 409` and
the `"already exists"` substring as a belt-and-suspenders.

### 7.4 Pretty-printed output / colors

`render.c(...)` wraps `click.style` and is used by every plan/diff
output. It honors Click's auto-detection (so output piped to a file
won't have ANSI codes). If you ever want a `--no-color` flag, do it at
the `c()` level.

### 7.5 Logger usage

The CLI uses the project-wide `cloudinary_cli.defaults.logger`. Provider
plans go through `logger.info`; warnings (skipped items, soft failures)
go through `logger.warning`; hard failures go through `logger.error`.
`logger.debug` carries per-item normalized diffs that only show up
under `-v`/`-vv`.

---

## 8. Testing notes

### 8.1 22 unit tests, all in `test/test_modules/test_cli_settings.py::TestCLISettings`

- Pure-Python, no live network. Heavy use of `unittest.mock.patch.object`.
- Important patching idiom: patch the *imported name in the consumer
module* when testing CLI flow:
  ```python
  patch.object(settings_commands, "diff_config_bundle", return_value=True)
  ```
  Patching the originating module won't intercept the call because
  `commands.py` imported the name at module-load time.

### 8.2 Integration tests are pre-existing and only cover SMD

`TestCLISettingsIntegration` is gated on
`cloudinary.config().api_secret and cloudinary.config().cloud_name`. With
real credentials it round-trips an SMD field+rule. New providers don't
have integration coverage yet — see §5.5.

### 8.3 Pre-existing failing tests in the repo (NOT this work)

Three test modules have pre-existing failures unrelated to settings:

- `test/test_cli_config.py::TestCLIConfig::test_cli_config_remove*`
- `test/test_modules/test_cli_clone.py::TestCLIClone::test_*` (calls
`clone.metadata.create_metadata_items` which no longer exists)
- `test/test_modules/test_cli_upload_dir.py::TestCLIUploadDir::test_*`
- `test/test_modules/test_cli_sync.py` (collection-time `cloudinary.api .config(settings="true")` requires network)

These were verified to fail on `master` without any settings changes.
Don't be alarmed; don't try to fix them as part of settings work.

### 8.4 Tests cover


| Layer              | Test                                                                                                                                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pick parser        | `test_parse_picks_all_sentinels`, `test_parse_picks_new_components`, `test_parse_picks_unsupported_group_raises`                                                                                                |
| envelope           | `test_envelope_v2_make_finalize_round_trip`, `test_envelope_load_v1_snapshot_upgrades_in_memory`, `test_envelope_previous_serial_for_lineage`                                                                   |
| dirstore           | `test_dirstore_round_trip`, `test_dirstore_missing_index_raises`                                                                                                                                                |
| registry           | `test_provider_registry_shape`                                                                                                                                                                                  |
| upload_presets     | `test_upload_presets_normalize_strips_noisy_and_sorts_lists`, `test_upload_presets_export_filters_with_pattern`                                                                                                 |
| streaming_profiles | `test_streaming_profiles_overridden_builtin_detection`, `test_streaming_profiles_summarize_marks_builtin_overrides`                                                                                             |
| upload_mappings    | `test_upload_mappings_needs_update`                                                                                                                                                                             |
| config             | `test_config_apply_bundle_refuses_with_warning`, `test_config_diff_bundle_detects_drift`                                                                                                                        |
| CLI                | `test_settings_save_out_file_is_pretty_and_file_only`, `test_settings_components_command_lists_all`, `test_settings_diff_invokes_apply_dry_run_for_components`, `test_settings_smd_delete_no_picks_deletes_all` |


---

## 9. Snapshot envelope: implementation specifics

### 9.1 Field order in `make_envelope`

Python 3.7+ preserves dict insertion order. We insert in a deliberately
human-readable order so the JSON file reads top-down: identity →
provenance → source → selection → metadata → bundles → fingerprints →
checksum (`finalize_envelope` appends the last two).

### 9.2 `lineage` is generated only on first save under a `<cloud>/<name>` pair

```python
prev_lineage, prev_serial = previous_serial_for_lineage(target_path)
snapshot = make_envelope(
    ...,
    lineage=prev_lineage,                              # None → fresh UUID
    serial=(prev_serial + 1) if prev_serial else 1,
)
```

If you `cp store/A.json store/B.json`, the `lineage` is preserved (it's
in the JSON body), but `cld settings save B` would *bump the serial of
B's existing lineage*, not start a fresh one. That's the right behavior
for the design's "stable across copies/renames" goal.

### 9.3 `compute_checksum` excludes envelope by construction

```python
payload = {k: snapshot.get(k) for k in component_keys if k in snapshot}
return _sha256(_canonical_json(payload))
```

We pass `ALL_COMPONENTS` as `component_keys`, so the checksum hashes
exactly the component bundles — never `lineage`, `serial`, `writer`, etc.
This means re-saving the same content with a bumped serial keeps the
checksum stable, which is what we want for "is this the same content?"
queries.

### 9.4 v1 loader is a soft upgrade

```python
def load_snapshot(snapshot):
    if schema in (None, 1):
        upgraded = dict(snapshot)
        upgraded.setdefault("schema_version", 1)        # NB: stays at 1
        upgraded.setdefault("lineage", None)
        upgraded.setdefault("serial", None)
        upgraded.setdefault("writer", None)
        upgraded.setdefault("metadata", {"notes": None, "tags": []})
        ...
        return upgraded
    return snapshot
```

Two non-obvious points:

- `schema_version` stays `1`. We deliberately don't pretend a v1 file is
v2. Callers that want to behave differently (e.g., refuse to operate
on v1 in some future strict mode) can check `schema_version`.
- The function returns a **shallow copy**, not the original. So writing
`snapshot["fingerprints"] = ...` after `load_snapshot(...)` doesn't
mutate the on-disk JSON.

### 9.5 Directory-mode envelope = "everything except component keys"

```python
envelope = {k: v for k, v in snapshot.items() if k not in component_keys}
write_json_to_file(envelope, os.path.join(directory, _INDEX_FILE), indent=2)
```

`_index.json` ends up holding `schema_version`, `type`, `name`, `lineage`,
`serial`, `created_at`, `writer`, `source`, `components`, `selection`,
`metadata`, `fingerprints`, `checksum`. The component keys (`smd`,
`transformations`, …) are filtered out and end up in their own
per-component files.

---

## 10. Adding a new provider — runbook

To add a new component (e.g., hypothetical `webhooks`):

1. Create `providers/webhooks.py`. At minimum:
  ```python
   COMPONENT = "webhooks"
   PICK_KINDS = ("event", "uri")        # or whichever apply
   PICK_ALL_SENTINEL = "__ALL_WEBHOOKS__"

   def export_bundle(*, picks=None, related=None) -> dict: ...
   def summarize_bundle(bundle) -> list[str]: ...
   def apply_bundle(bundle, *, target_options=None, picks=None, related=None,
                    mode="create-missing", dry_run=False, force=False) -> bool: ...
   # optional:
   def delete_items(*, target_options=None, picks=None, related=None,
                    dry_run=False, force=False) -> bool: ...
  ```
2. Register in `providers/__init__.py`:
  - Import the module.
  - Add to `PROVIDERS`.
  - Insert into `APPLY_ORDER` *at the right position* (think about
  dependencies on / from existing components).
  - Add to `ALL_COMPONENTS` and (if it's part of the default save set)
  `DEFAULT_COMPONENTS`.
3. Extend `utils/pick.py`:
  - Add the group to `SUPPORTED_PICK_GROUPS`.
  - Add a `SUPPORTED_<component>_PICK_KINDS` tuple.
  - Add a `<component>_PICK_ALL_SENTINEL`.
  - Wire a branch into `parse_picks` matching the existing pattern.
  - Add a slot to the `Picks` class.
  - Wire it through `Picks.for_component`.
4. Wire into `commands.py`:
  - Import the public functions and the sentinel from
   `.providers.webhooks`.
  - Add a `_<component>_filters(...)` helper if non-trivial.
  - Add the component to the per-component summary in
  `_print_per_component_summary`.
  - Add export branch in `save_settings` and `clone_settings`.
  - Add per-component delete subgroup
  (`@settings.group("webhooks", ...)` + a `delete` command).
  - Update `_picks_for(component, parsed)` and `_apply_to_target` so
  `restore`/`clone`/`diff` route picks through correctly.
5. Add unit tests in `test/test_modules/test_cli_settings.py`:
  - normalization equality
  - export pattern filtering
  - apply mode plan correctness for `create-missing` / `upsert` / `sync`
  - registry shape (`test_provider_registry_shape` will break unless
  you've added the component to `expected`).
6. Update both user-facing docs:
  - Add a row to the components table in `[docs/settings.md](settings.md)`.
  - Mention the provider in the "Per-component reference" section.
  - Add a CHANGELOG entry under Unreleased.
7. Update this file with anything component-specific.

---

## 11. Backward compatibility

- v1 snapshots load unchanged via `load_snapshot`. They never get
re-saved as v1 — re-saving through `cld settings save` produces a v2
envelope.
- The legacy `(selected_components, smd_fields, smd_rules, transformation_names) = parse_picks(...)` 4-tuple still unpacks via
`Picks.__iter__`. The legacy SMD-only code paths in `commands.py`
still work.
- `__ALL__` (the legacy "all-of-SMD" sentinel) is recognized everywhere
alongside the new per-component sentinels.

If you ever bump to a v3 envelope, the right move is to extend
`load_snapshot` with a new branch *and* keep the v1/v2 branches working —
removing back-compat is a much bigger decision than adding it.

---

## 12. Cross-references

- Design: `[docs/settings-design.md](settings-design.md)` — the spec.
- User guide: `[docs/settings.md](settings.md)` — for end-users.
- CHANGELOG entry: under "Unreleased" in
`[CHANGELOG.md](../CHANGELOG.md)`.
- README pointer: `### settings` section in
`[README.md](../README.md)`.

