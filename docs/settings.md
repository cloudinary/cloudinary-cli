# `cld settings` — User Guide

The `settings` command set saves, restores, diffs, and clones Cloudinary
**product‑environment configuration** between accounts and snapshots. Use it
to:

- Back up structured metadata, transformations, presets, and more before a
  risky change.
- Promote settings from staging to production with a reviewable plan.
- Detect drift between an environment and a known-good baseline.
- Clone a curated subset of settings into one or more target accounts.
- Track configuration in Git via a per-component directory layout.

Six components are supported today:

| Component             | Identity         | Captured                                                | Applicable |
|-----------------------|------------------|---------------------------------------------------------|------------|
| `smd`                 | `external_id` / rule name | Structured Metadata fields and rules            | yes |
| `transformations`     | name             | Named transformations (with allowed-for-strict)         | yes |
| `upload_presets`      | name             | Upload presets (signed/unsigned, full settings)         | yes |
| `streaming_profiles`  | name             | Custom profiles + overridden built-ins                  | yes |
| `upload_mappings`     | `folder`         | Auto-upload mappings (`folder` ➝ `template`)            | yes |
| `config`              | (singleton)      | Product environment config (`folder_mode`, …)           | read/diff only |

> **Heads-up about `config`** — the Admin API only exposes *reads* for
> product‑environment config. It is captured by every save (handy for
> diffing/auditing) but never auto-applied. Change values from the Console or
> through the Provisioning API.

---

## Table of contents

1. [Quick start](#quick-start)
2. [Core concepts](#core-concepts)
3. [Selecting items: `--pick`](#selecting-items---pick)
4. [Apply modes](#apply-modes)
5. [Snapshot files](#snapshot-files)
6. [Commands reference](#commands-reference)
7. [Per-component reference](#per-component-reference)
8. [Common workflows](#common-workflows)
9. [Snapshot envelope (v2)](#snapshot-envelope-v2)
10. [Tips and FAQ](#tips-and-faq)

---

## Quick start

```bash
# 1. Inspect what's available.
cld settings components

# 2. Take a full snapshot of the current environment, save it to the local store.
cld settings save prod-baseline --note "promoted from staging"

# 3. List your saved snapshots.
cld settings ls

# 4. See what would change if you applied that snapshot to the current account
#    (no writes; just a plan).
cld settings diff prod-baseline

# 5. Apply it to a different account (--mode upsert updates existing items too).
cld settings clone --from prod-baseline --mode upsert prod_account_config

# 6. Roll back: restore the baseline back into the current account.
cld settings restore prod-baseline --mode sync --dry-run    # preview
cld settings restore prod-baseline --mode sync              # apply
```

---

## Core concepts

### Snapshot

A **snapshot** is a JSON document (or directory of JSON files) that contains
zero or more **component bundles** plus an **envelope** with metadata
(timestamp, lineage, fingerprints, etc.). See
[Snapshot envelope (v2)](#snapshot-envelope-v2).

Snapshots can live in three places:

| Where                | Flag                | Path                                                        |
|----------------------|---------------------|-------------------------------------------------------------|
| Local store          | (default)           | `~/.cloudinary-cli/settings/<cloud_name>/<name>.json`       |
| Single file          | `--out`/`--in`      | Wherever you point them                                     |
| Per-component dir    | `--out-dir`/`--in-dir` | `<dir>/_index.json` + `<dir>/<component>.json`           |

The store is the most ergonomic for personal workflows and CI agents that
have a stable home directory; explicit files are best for sharing or
attaching to a PR; directory layout is best for Git.

### Components

Pass `--component <name>` to limit which components a command touches.
Without `--component`, the default is **all six** for `save`, and **whatever
is present in the snapshot** for `restore`/`clone`/`diff`.

```bash
cld settings save \
  --component smd \
  --component transformations \
  --component upload_presets
```

You can repeat `--component` to combine multiple, or rely on `--pick` (below)
which implicitly selects components based on what you pick.

### Selection (`--pick`)

`--pick` is a 3-tuple option: `--pick <group> <kind> <value>`. It’s
repeatable. Each component supports its own kinds — see
[the pick reference](#selecting-items---pick).

### Apply modes

Three modes control how `restore`/`clone` reconcile the snapshot with the
target account:

| Mode             | Creates missing | Updates existing | Deletes extras (in target but not in snapshot) |
|------------------|-----------------|------------------|------------------------------------------------|
| `create-missing` | yes             | no               | no                                             |
| `upsert`         | yes             | yes              | no                                             |
| `sync`           | yes             | yes              | yes                                            |

The default is `create-missing`. Use `--dry-run` to preview the plan
without writing anything.

### Apply order

Applies happen in this order regardless of how the user listed components,
because some components depend on others (e.g., upload presets reference
metadata fields):

```
upload_mappings → streaming_profiles → transformations → smd → upload_presets → config
```

`config` is always last and never modifies the target — it only logs a
warning that explains where to make changes manually.

---

## Selecting items: `--pick`

Picks share a 3-token format:

```
--pick <group> <kind> <value>
```

| Group                | Kinds                  | Identity used      |
|----------------------|------------------------|--------------------|
| `smd`                | `field`, `rule`        | `external_id` / rule name |
| `transformations`    | `name`                 | transformation name |
| `upload_presets`     | `name`                 | preset name        |
| `streaming_profiles` | `name`                 | profile name       |
| `upload_mappings`    | `folder`               | folder             |

Wildcards are supported via `fnmatch` patterns: `*`, `?`, `[abc]`. The
literal value `*` or `all` means **everything in that group**.

Examples:

```bash
# Save a single SMD rule, plus all upload presets that start with "checkout-".
cld settings save promo \
  --pick smd rule "Editorial workflow" \
  --pick upload_presets name "checkout-*"

# Diff only one transformation against the live account.
cld settings diff baseline --pick transformations name "thumb_400"

# Restore everything for streaming profiles, but only the "incoming/" mapping.
cld settings restore baseline \
  --pick streaming_profiles name "*" \
  --pick upload_mappings folder "incoming/"

# Use --pick to implicitly select components: this restores SMD only.
cld settings restore baseline --pick smd field "*"
```

Combine `--pick` with `--component` to be explicit. If you pass picks but no
`--component`, the components are inferred from the picks’ groups.

---

## Apply modes

You set the mode with `--mode <mode>`:

- **`create-missing`** *(default)* — only adds items that don’t exist.
  This is the safest mode and ignores any drift on existing items.
- **`upsert`** — also updates existing items so they match the snapshot.
  Does not delete anything.
- **`sync`** — additionally deletes items present in the target but absent
  from the snapshot. Use carefully — pair with `--pick` to scope it.

`--dry-run` works with any mode: the plan is printed and confirmed but
nothing is written.

---

## Snapshot files

### Single-file mode

Default. One JSON file per snapshot. Self-contained and easy to share.

```bash
cld settings save my-baseline --out ./bundle.json
```

### Directory mode (Git-friendly)

Useful when you want a tidy diff per component in version control.

```
settings/
├─ _index.json              # envelope: name, lineage, serial, writer, fingerprints, checksum
├─ smd.json                 # component bundle
├─ transformations.json
├─ upload_presets.json
├─ streaming_profiles.json
├─ upload_mappings.json
└─ config.json
```

```bash
cld settings save --out-dir ./settings/
cld settings diff --in-dir ./settings/
cld settings restore --in-dir ./settings/ --mode sync --dry-run
```

Reading a directory with a missing component file is fine — that component
is treated as "not present in the snapshot".

### Local store

When you save without `--out`/`--out-dir`, the snapshot lands in
`~/.cloudinary-cli/settings/<cloud_name>/<snapshot_name>.json`.

```bash
cld settings folder            # print the store path
cld settings folder --open     # open it in Finder/Files
cld settings ls                # list saved snapshots across all clouds
cld settings ls --cloud demo   # list only one cloud
cld settings show prod-baseline
cld settings rm  prod-baseline
```

---

## Commands reference

All commands accept `-h` / `--help`. The flags below are grouped by purpose.

### `cld settings save [NAME]`

Save the current account's settings to the local store, a file, or a
directory.

```
--component TEXT         Components to include. Repeatable.
--pick    TEXT TEXT TEXT Selection (group, kind, value). Repeatable.
--smd-include-rules      When --picking SMD fields, also include rules
                         that reference them.
--out TEXT               Write to file path (single-file mode).
--out-dir TEXT           Write per-component directory layout.
--note TEXT              Free-form note recorded in metadata.
--tag TEXT               Tag for `ls --tag` filtering. Repeatable.
-F, --force              Overwrite existing snapshot without prompting.
```

Behavior:

- If `NAME` is omitted, an interactive prompt suggests one based on the
  cloud name, components, and timestamp. In a non-TTY (CI) context the
  default name is used.
- If a snapshot with the same name already exists in the store, its
  `lineage` is preserved and `serial` is bumped. Otherwise a fresh
  `lineage` is generated.
- After writing, per-component fingerprints (sha256) and a top-level
  checksum are computed and stored in the envelope (see
  [Snapshot envelope](#snapshot-envelope-v2)).

Examples:

```bash
# Whole environment to the store, with metadata.
cld settings save prod-baseline --note "approved by SRE on 2026-04-15" \
  --tag prod --tag baseline

# Selective save to a file (great for PR review).
cld settings save \
  --component smd --component upload_presets \
  --pick smd rule "Editorial workflow" \
  --pick upload_presets name "checkout-*" \
  --out ./changes.json

# Track in Git.
cld settings save --out-dir ./settings/ --force
git add settings/ && git commit -m "settings: snapshot prod"
```

### `cld settings ls`

List snapshots in the local store.

```
--cloud TEXT     Filter by cloud name.
--tag TEXT       Show only snapshots whose metadata.tags contain ALL of these. Repeatable.
--json           Print rich JSON (cloud, lineage, serial, tags, notes, …).
```

Plain output is `<cloud_name>\t<name>` (or
`<cloud_name>\t<name>\t<serial>\t<tags>` when filters/JSON are involved).

### `cld settings show NAME`

Print a saved snapshot as JSON. Add `--out PATH` to also write a copy.

### `cld settings rm NAME`

Delete a snapshot from the local store. Add `-F` to skip the prompt.

### `cld settings folder`

Print the store directory path. Add `--open` to open it.

### `cld settings components`

List supported components, their pick kinds, and whether each one supports
`apply`/`delete`.

```
--json           Output JSON.
```

### `cld settings diff [NAME]`

Show **drift** between a snapshot and a target account (defaults to the
current account). For non-config components this runs each provider's
planner in `mode=sync, dry_run=true` (so all three buckets — create, update,
delete — are visible). For `config` it calls the read-only diff.

```
--in TEXT             Diff a file path instead of a stored snapshot.
--in-dir TEXT         Diff a directory layout.
--cloud TEXT          Cloud namespace for stored snapshot lookup.
--component TEXT      Restrict to specific components. Repeatable.
--pick TEXT TEXT TEXT Restrict to specific items.
```

Returns non-zero exit if drift is found, so you can use it in CI:

```bash
cld settings diff prod-baseline >diff.log 2>&1
if [ $? -ne 0 ]; then echo "drift detected, see diff.log"; fi
```

### `cld settings config diff [NAME]`

Convenience alias for `cld settings diff --component config …`.

### `cld settings restore [NAME]`

Apply a snapshot to the **current** account.

```
--cloud TEXT          Cloud namespace for stored snapshot lookup.
--in TEXT             Restore from a file path.
--in-dir TEXT         Restore from a directory layout.
--component TEXT      Restrict to specific components. Repeatable.
--pick TEXT TEXT TEXT Restrict to specific items.
--smd-include-rules   When picking SMD fields, also include their rules.
--mode [create-missing|upsert|sync]   default: create-missing
--dry-run             Show the plan; don't write.
-F, --force           Skip confirmation.
```

If you call `restore` with no `NAME` and no `--in*`, an interactive picker
lists snapshots for the current cloud. In CI, always pass an explicit name
or path.

### `cld settings clone TARGETS…`

Apply settings to **one or more target accounts**. Targets can be a saved
config name (see `cld config`) or a `cloudinary://…` URL.

```
--from TEXT           Use a stored snapshot as the source.
--cloud TEXT          Cloud namespace for `--from`.
--in TEXT             Use a snapshot file as the source.
--in-dir TEXT         Use a snapshot directory as the source.
--component TEXT      Restrict to specific components.
--pick TEXT TEXT TEXT Restrict to specific items.
--smd-include-rules   See restore.
--mode [create-missing|upsert|sync]   default: create-missing
--dry-run             Show the plan; don't write.
-F, --force           Skip confirmation.
```

Without `--from`/`--in`/`--in-dir`, `clone` exports a *fresh ad-hoc
snapshot* from the current account and pushes it to each target. This is
the most common form when promoting changes from a working environment to
production.

Examples:

```bash
# Promote everything that exists in staging to prod and dev.
cld settings clone prod dev

# Promote only specific items, with sync semantics, scoped via picks.
cld settings clone prod \
  --pick smd rule "Editorial workflow" \
  --pick upload_presets name "checkout-*" \
  --mode sync

# Use a previously saved baseline (stored under the staging cloud) and apply
# it to two prod accounts; explicit URL is also fine.
cld settings clone --from staging-baseline --cloud staging prod1 \
  cloudinary://API_KEY:API_SECRET@prod2_cloud
```

### Per-component admin helpers

These bypass snapshots and operate directly on the current account.

#### `cld settings smd delete`

```
--pick TEXT TEXT TEXT  Optional. Without --pick, deletes ALL fields and rules.
--smd-include-rules    Also delete rules referencing the picked fields.
--dry-run / -F
```

#### `cld settings transformations delete NAMES…`

Names can also come from `--pick transformations name <value>`. Wildcards
allowed.

#### `cld settings upload-presets delete NAMES…`

```
--pick upload_presets name <value>   (repeatable)
```

#### `cld settings streaming-profiles delete NAMES…`

```
--allow-revert-builtins  Required to delete a built-in profile (which
                         reverts the override). Without it, built-ins are
                         skipped with a warning.
```

#### `cld settings upload-mappings delete FOLDERS…`

```
--pick upload_mappings folder <value>  (repeatable)
```

---

## Per-component reference

### `smd` — Structured Metadata

- **What's captured:** all metadata fields and rules (or only the ones you
  pick). Datasource values are captured for enum/set fields.
- **Identity:** field `external_id`, rule `name`.
- **Datasource semantics:** on apply, missing options are added; existing
  options are preserved; in `sync` mode, options not in the snapshot are
  marked inactive (Cloudinary keeps them as `state: "inactive"` rather
  than deleting). This keeps historical data referenced by older assets
  intact.
- **Field/rule ordering:** fields are applied first, then rules. If a rule
  references a field not yet present and that field isn’t selected,
  the rule is skipped with a warning. Use `--smd-include-rules` to
  auto-include the related rules whenever you pick a field.
- **Pick kinds:** `field`, `rule`. Wildcards work on names.

```bash
# Save only the workflow-related rule, automatically including the fields it depends on.
cld settings save workflow \
  --pick smd rule "Editorial workflow"

# Mass-deactivate a stale option family on the field "status" by syncing from a baseline.
cld settings restore status-baseline --pick smd field status --mode sync
```

### `transformations` — Named transformations

- **What's captured:** named transformations and `allowed_for_strict`.
  Cloudinary-managed (auto, derived) transformations are not captured.
- **Identity:** transformation name.
- **Normalization:** transformation chains are canonicalized for stable
  comparison.
- **Pick kinds:** `name`.

```bash
# Save just the thumbnail family.
cld settings save thumbs --pick transformations name "thumb_*"

# Promote them to prod with upsert.
cld settings clone prod --from thumbs --mode upsert
```

### `upload_presets` — Upload presets

- **What's captured:** name, `unsigned` flag, full `settings` body
  (incoming transformations, eager, tags, allowed_formats, etc.).
- **Identity:** preset name.
- **Normalization:** server-assigned keys (`external_id`, `created_at`,
  `updated_at`) are stripped. List-like fields (`tags`, `allowed_formats`)
  are sorted for stable equality. The original (unsorted) value is what's
  sent on apply.
- **Pick kinds:** `name`.

```bash
# Promote the unsigned demo preset and the checkout family.
cld settings clone prod \
  --pick upload_presets name "demo_unsigned" \
  --pick upload_presets name "checkout-*" \
  --mode upsert
```

### `streaming_profiles` — Streaming profiles

- **Two flavors:**
  - **Custom** profiles (`predefined: false`) are fully owned by you;
    create/update/delete are all available.
  - **Built-in** profiles (`predefined: true`, e.g. `4k`, `hd`) ship with
    Cloudinary defaults. They’re only captured in the snapshot if your
    account has *overridden* their representations. On apply, only the
    `update` operation is issued; built-ins are never created or deleted
    by `restore`/`clone`.
- **Reverting a built-in override:** use the per-component delete helper
  with explicit opt-in:

  ```bash
  cld settings streaming-profiles delete hd --allow-revert-builtins
  ```

- **Pick kinds:** `name` (matches both flavors).

> The defaults table used to detect overrides is hard-coded in the CLI.
> If Cloudinary publishes new built-ins or changes the defaults, the CLI
> may classify a name as “overridden” to be safe; check the design doc
> §6.4 for the verifier.

### `upload_mappings` — Auto-upload mappings

- **What's captured:** `folder` ➝ `template`.
- **Identity:** `folder`.
- **Pick kinds:** `folder`.

```bash
cld settings save mappings --component upload_mappings
```

### `config` — Product environment config

- **Read/diff only.** Apply is refused with a warning.
- **What's captured:** `cloud_name`, `created_at`, and `settings` (notably
  `folder_mode`).
- The captured settings are also mirrored into `source.config_settings`
  for convenience.
- Use `cld settings diff --component config` (or its alias
  `cld settings config diff`) to detect drift.

```bash
cld settings save baseline --component config
# … later …
cld settings config diff baseline
```

---

## Common workflows

### 1. Promote staging → prod (no surprises)

```bash
# 1. Capture the staging account.
CLOUDINARY_URL=$STAGING_URL  cld settings save staging-baseline --tag promotion

# 2. Preview what would change in prod, in upsert mode.
CLOUDINARY_URL=$PROD_URL  cld settings restore staging-baseline \
  --cloud staging --mode upsert --dry-run

# 3. Apply.
CLOUDINARY_URL=$PROD_URL  cld settings restore staging-baseline \
  --cloud staging --mode upsert -F
```

Or as a single command:

```bash
cld settings clone --from staging-baseline --cloud staging --mode upsert prod
```

### 2. Pre-change checkpoint + post-change verification

```bash
cld settings save before-change --note "before adding new SMD field"
# … make changes via Console / Admin API …
cld settings diff before-change   # drift summary
```

### 3. Track settings in Git

```bash
cld settings save --out-dir ./settings/ --force --tag canonical
git add settings/
git commit -m "settings: refresh canonical baseline"
```

In CI, fail the build if the live environment drifts from the committed
baseline:

```bash
cld settings diff --in-dir ./settings/ || exit 1
```

### 4. Clone a curated subset

```bash
cld settings clone prod \
  --component smd --component upload_presets \
  --pick smd rule "Editorial workflow" \
  --pick upload_presets name "checkout-*" \
  --mode sync --dry-run
```

`sync` deletes target items in the picked groups that are absent from the
source, so this is the safest way to enforce *exactly these* presets in
prod.

### 5. Revert an overridden built-in streaming profile

```bash
# Show what changed.
cld settings diff baseline --pick streaming_profiles name hd

# Revert.
cld settings streaming-profiles delete hd --allow-revert-builtins
```

### 6. Audit drift weekly (cron / CI)

```bash
cld settings diff prod-baseline --json >drift.json || alert "drift detected"
```

### 7. Recover from a regression

```bash
cld settings restore prod-baseline --mode sync --dry-run
cld settings restore prod-baseline --mode sync -F
```

---

## Snapshot envelope (v2)

Each snapshot is a JSON object with these envelope fields plus
component bundles keyed by component name:

```jsonc
{
  "schema_version": 2,
  "type": "settings_snapshot",
  "name": "prod-baseline",
  "lineage": "5b9f1e87-…",                // stable across copies/renames
  "serial":  3,                            // bumps on overwrite within a lineage
  "created_at": "2026-04-27T11:08:31+03:00",
  "writer": {
    "cli_version": "1.13.0",
    "sdk_version": "1.44.1",
    "user": "alice@laptop"
  },
  "source": {
    "cloud_name": "demo-cloud",
    "config_settings": { "folder_mode": "fixed" }   // present iff config was captured
  },
  "components": ["smd", "transformations", "upload_presets", "streaming_profiles", "upload_mappings", "config"],
  "selection": {                          // exact --component / --pick the user passed
    "components": ["smd"],
    "picks": [["smd","rule","Editorial workflow"]]
  },
  "metadata": {
    "notes": "promoted from staging",
    "tags":  ["prod","baseline"]
  },
  "fingerprints": {                       // sha256 over canonical-JSON of each bundle
    "smd": "sha256:9a78…",
    "transformations": "sha256:…"
  },
  "checksum": "sha256:…",                 // sha256 over canonical-JSON of all bundles

  "smd":                { "fields": [...], "rules": [...] },
  "transformations":    { "transformations": [...] },
  "upload_presets":     { "presets": [...] },
  "streaming_profiles": { "custom_profiles": [...], "overridden_builtins": [...] },
  "upload_mappings":    { "mappings": [...] },
  "config":             { "settings": {...}, "applicable": false }
}
```

### Lineage and serial

- `lineage` is a UUID generated on first save under a given `<cloud>/<name>`
  pair. It survives renames if you copy the file to a new name yourself,
  but a fresh `cld settings save` to a *different* `<name>` starts a new
  lineage.
- `serial` increases by 1 every time you overwrite a snapshot in the
  store under the same `<cloud>/<name>`. It’s a simple way to tell
  "newer" from "older" within the same line.

### Fingerprints and checksums

- `fingerprints[<component>]` lets you compare individual bundles
  efficiently — e.g., to skip applying components that are already
  identical.
- `checksum` lets you assert end-to-end integrity of the snapshot. If a
  snapshot was edited by hand, recompute it via `cld settings save
  --out-dir <existing>` (or by re-running through the loader).

### v1 backwards compatibility

Older snapshots (the SMD-only `schema_version: 1` files) load transparently
— the CLI fills in missing envelope fields with `None` and infers the
component list from the keys actually present, so `restore` / `diff` /
`clone` keep working unchanged. v1 snapshots are *not* mutated on disk.

---

## Tips and FAQ

**Q: Where are snapshots stored?**
A: `~/.cloudinary-cli/settings/<cloud_name>/<name>.json`. Run `cld settings folder` to print the path or `cld settings folder --open` to open it.

**Q: Can I keep snapshots in Git?**
A: Yes — use `--out-dir` for a per-component directory layout. The `_index.json` file holds the envelope; each component is in its own JSON. Diffs are component-scoped and Git-friendly.

**Q: Can I edit a snapshot by hand?**
A: Yes, but the `fingerprints` and `checksum` will go stale. Either regenerate them by saving through the CLI again, or accept that downstream integrity checks will fail.

**Q: How is `restore` different from `clone`?**
A: `restore` always targets the *current* account configured by `CLOUDINARY_URL` / `cld config`. `clone` accepts one or more *target* accounts (saved config names or `cloudinary://…` URLs) and applies the snapshot to each.

**Q: What if a component fails partway through?**
A: Each component is applied independently. A failure in one component does not roll back earlier components, but the CLI reports a non-zero exit and logs which components failed. You can re-run with `--component` to retry just the failed ones.

**Q: Why didn't my rule restore?**
A: Rules require their referenced fields to exist on the target. Either include those fields in your selection, or use `--smd-include-rules` to opt in to automatic inclusion.

**Q: Can I capture only the items that match a name pattern?**
A: Yes — wildcards (`*`, `?`, `[abc]`) are supported in `--pick`. They’re evaluated client-side via `fnmatch`.

**Q: Is `sync` mode safe?**
A: Only when scoped. Without `--pick` or `--component`, `sync` will delete from the target anything that isn't in the snapshot. Always run with `--dry-run` first.

**Q: Why is `config` included in saves but not restores?**
A: The Admin API only exposes reads for product-environment config; writes belong to the Provisioning API. Capturing it in saves makes it useful for diffing/auditing, even though apply is intentionally a no-op.

**Q: What does an overridden built-in streaming profile look like?**
A: Any built-in (`predefined: true`) whose `representations` differ from the published defaults. The CLI captures only the override and reapplies it via `update`. To revert, use `cld settings streaming-profiles delete <name> --allow-revert-builtins`.

**Q: Can I run this in CI without prompts?**
A: Yes — pass `-F` (force) and an explicit `NAME` or `--in*`. With `--dry-run`, you can wire diffs into a guard step that fails the build when drift is detected.

**Q: What changed between v1 and v2?**
A: v1 was SMD-only. v2 adds: multi-component bundles, the `lineage`/`serial`/`writer`/`selection`/`metadata` envelope fields, per-component `fingerprints`, a top-level `checksum`, and the directory layout. v1 snapshots still load.

---

## See also

- `cld settings --help` and each subcommand’s `--help` for the canonical
  flag listings.
- [`docs/settings-design.md`](settings-design.md) for the architectural
  design and rationale.
- [`docs/settings-implementation.md`](settings-implementation.md) for
  maintainer-oriented implementation notes (decisions, divergences,
  stubs/TODOs, runbook for adding a provider).
- [Cloudinary Admin API documentation](https://cloudinary.com/documentation/admin_api) for the underlying endpoints each provider uses.
