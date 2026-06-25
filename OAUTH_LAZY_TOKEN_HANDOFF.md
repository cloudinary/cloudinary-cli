# Self-refreshing OAuth token — implementation & handoff

> **For the next agent.** This is the implementation that replaces the scattered
> `ensure_active_config_fresh()` lazy-refresh hooks with a single self-refreshing `oauth_token` on
> the active config object. It builds on the change documented in
> `OAUTH_DEFAULT_CONFIG_IMPLEMENTATION.md` (commit `43fb67a`, branch `oauth-login`) and the design
> rationale in `OAUTH_LAZY_TOKEN_PROPERTY_DESIGN.md` + `OAUTH_LAZY_TOKEN_CAVEATS_AND_MTIME.md`.
> Concurrency analysis that motivated the redesign is in `OAUTH_REFRESH_CONCURRENCY_REVIEW.md`.
>
> Read `OAUTH_LAZY_TOKEN_PROPERTY_DESIGN.md` first for the "why"; this doc is the "what landed".

---

## 1. What changed and why

### The problem (see `OAUTH_REFRESH_CONCURRENCY_REVIEW.md`)
The previous design refreshed a stale OAuth token via `ensure_active_config_fresh()` called at four
hand-maintained API chokepoints (`call_api`, `execute_single_request`, `query_cld_folder`,
`cld_folder_exists`). Problems: per-call `load_config()` on the hot path; a hand-maintained
chokepoint list that silently misses new API paths (→ stale-token 401 mid-bulk-run); and a
`reset_config()`-based global swap that races with worker threads under `sync`/`upload-dir`.

### The fix
Access tokens live ~5 minutes, so refreshes are frequent and expected. Instead of probing before
every call, the **active config's `oauth_token` refreshes itself when the SDK reads it** at request
time. The SDK reads `cloudinary.config().oauth_token` per request (`call_api.py:63`,
`uploader.py:877`) — one universal seam.

- **New `cloudinary_cli/auth/oauth_config.py`** — `OAuthConfig(cloudinary.Config)`:
  - `oauth_token` is a **property** (class-level data descriptor; overrides `__dict__` on read,
    which a `__getattr__` hook could not — the SDK stores the token in `__dict__`).
  - On read: if the in-object parsed `_session` is fresh (or has no refresh token), return the
    stored token with **no I/O**. Only when stale does it `load_config()` + call
    `refresh_url_if_stale` (the existing lock + double-check + atomic persist, reused verbatim),
    update the in-object token, and return it. Subsequent reads short-circuit on the now-fresh
    `_session` — **no per-call disk read or lock once fresh.**
  - It does **not** `reset_config()` inside the getter (avoids the global-swap thread race and
    self-destruction of the executing object). It mutates only its own fields.
  - `has_oauth` property — token *presence* without refreshing. Used by all type/validity checks.
  - `from_env()` / `from_url()` factories + `install_oauth_config()` / `install_env_config()`:
    **every** active config the CLI installs is now an `OAuthConfig` (saved, env-fallback, and
    inline `-c`), so `has_oauth` is universal and the resolver's env branch installs a static
    (never-refreshing) OAuthConfig.
- **Deleted** `ensure_active_config_fresh()` and all four call sites (`core/search.py`,
  `utils/api_utils.py` ×3).
- **`config_utils.refresh_cloudinary_config(url, saved_name=None)`** now delegates to
  `install_oauth_config` (single install seam).
- **mtime cache in `load_config()`** — caches the parsed dict keyed on `(st_mtime_ns, st_size)`,
  returns a **copy** (callers mutate in place), invalidated in `save_config`. Cuts the remaining
  redundant reads (group-level validity check, `-ls`, refresh sweeps).
- **Classifiers consolidated** — `config_listing.config_type_label(obj)` is now
  `"oauth" if obj.has_oauth else "api_key"` (no `__dict__` peeking, no `getattr` fallback);
  `is_valid_cloudinary_config` reads `has_oauth` (lazily, without evaluating the refreshing
  property — see Caveat A).

### Caveats handled (detail in `OAUTH_LAZY_TOKEN_CAVEATS_AND_MTIME.md`)
- **A — truthiness reads must not refresh.** Type/validity/`-ls` read `has_oauth` (presence), never
  the refreshing `oauth_token`. NOTE: do **not** write `getattr(cfg, "has_oauth", bool(cfg.oauth_token))`
  — the default arg is evaluated eagerly and *would* trigger a refresh. Use a `hasattr` guard.
- **B — no `reset_config()` in the getter.** Refresh in place; the only global swap is at install
  time, once per process.

---

## 2. Test fixes in this commit (all pre-existing isolation bugs, surfaced by the refactor)

1. **`test_auth_session.py`** — `test_stale_refreshes_and_rewrites` / `test_refresh_timeout_returns_stale_url`
   did not patch `load_config`, so they read/wrote the developer's **real** `~/.cloudinary-cli/config.json`.
   This had previously **poisoned a real config entry** (`eu-cloud`) with MagicMock garbage. Both now
   patch `load_config`. (The poisoned entry was removed from the dev machine.)
2. **`test_cli_config.py::test_cli_config_show_default_no_config`** — asserts the "nothing
   configured" path but passed on base only via cross-`invoke` global pollution. Now clears
   `CLOUDINARY_*` env (via `patch.dict(..., clear=True)` over a filtered env) so it genuinely tests
   the unconfigured path. The new resolver behavior (env re-read on resolve) is *more* correct;
   this test just needed a clean env to assert the negative case.
3. **`test_cli_config_oauth.py::TestConfigSecretMasking`** — built `cloudinary.Config()` which
   auto-loads the dev env; when `CLOUDINARY_CLOUD_NAME`+`CLOUDINARY_ACCOUNT_URL` are set (common
   PyCharm setup), a real `account_url` leaked in, adding a 2nd `echo` call so the assertions
   (reading only the last call) missed the masked fields → **4 failures on the developer's machine**.
   Fixed by extending `_RestoresSdkConfig` to strip `CLOUDINARY_*` in `setUp` and inheriting it.
4. **`TestEnsureActiveConfigFresh` → `TestSelfRefreshingOAuthToken`** — rewritten for the new model:
   presence check (`has_oauth`) does no network; reading `oauth_token` refreshes once; env/`-c`/api-key
   never refresh. Plus `test_presence_check_does_not_refresh` as the Caveat-A regression guard.
5. **Skip gating for offline/no-account runs** — `helper_test.CONFIG_PRESENT` / `REQUIRES_CONFIG`,
   applied per-method via `@unittest.skipUnless` to the 13 tests that mock HTTP but still need a
   resolvable config (`test_cli_url`, `test_cli_utils`, `test_cli_search_api`, `test_cli_api`). They
   now **skip** cleanly on a bare machine instead of failing.

### Test status
- **No config (bare machine):** 191 passed, 21 skipped, 0 failed.
- **Real test cloud (via `tools/allocate_test_cloud.sh`):** 211 passed, 1 skipped (`test_provisioning`,
  needs `account_id`), 0 failed.
- **Account-enabled dev env:** the 4 masking failures are fixed; remaining `test_cli_config` failures
  there are only because the simulated creds were fake (401) — they pass against a real account.

---

## 3. What is NOT done — for the next agent

These were identified in the reviews but are **out of scope of this commit**:

1. **Thread-safety of the refresh under `sync`/`upload-dir` (the original concern in
   `OAUTH_REFRESH_CONCURRENCY_REVIEW.md` §2).** The cross-process single-flight (lock + double-check)
   is correct and preserved. But the in-process getter, when stale, can have N worker threads enter
   `refresh_url_if_stale` together; they serialize on the reentrant `config_lock` and all but one
   adopt the peer-refreshed token (correct, but a synchronized stall). Consider a process-local
   `threading.Lock` around the getter's stale branch so only one thread per process attempts it.
2. **Refresh-on-401 retry (`OAUTH_REFRESH_CONCURRENCY_REVIEW.md` Fix C).** The lazy property closes
   the "stale at request build time" gap, but a token that expires *mid-flight* (between read and
   server receipt) still 401s with no retry. A reactive retry at `call_api` would be the robust
   complement.
3. **Transactional multi-step config ops (Fix D).** `login` + auto-default and refresh-and-default
   still read-decide-write across separate `config_lock` scopes (TOCTOU). Wrap in one lock scope.
4. **"config removed mid-run" message (Fix E).** The getter returns the stale token if the saved
   config vanished underneath it; surface a clear "re-login" error instead of a later raw 401.
5. **Chokepoint-completeness is now moot** (the property covers all read paths), but a test that
   asserts the active config is always an `OAuthConfig` post-resolve would lock that invariant in.
6. **`reset_config()` audit.** Verified the resolver/install paths, but any *future* direct
   `cloudinary.reset_config()` call would replace the OAuthConfig with a plain Config and silently
   disable self-refresh. Keep all config installation routed through
   `oauth_config.install_oauth_config` / `install_env_config`.

---

## 4. Key files

| File | Role |
|---|---|
| `cloudinary_cli/auth/oauth_config.py` | **New.** `OAuthConfig`, `has_oauth`, install seams. |
| `cloudinary_cli/utils/config_resolver.py` | Installs OAuthConfig per branch; `ensure_active_config_fresh` deleted. |
| `cloudinary_cli/utils/config_utils.py` | `refresh_cloudinary_config` delegates to install; mtime cache; `is_valid_cloudinary_config` via has_oauth. |
| `cloudinary_cli/utils/config_listing.py` | `config_type_label(obj)` → `has_oauth`. |
| `cloudinary_cli/utils/api_utils.py`, `core/search.py` | Chokepoint calls removed. |
| `test/helper_test.py` | `CONFIG_PRESENT` / `REQUIRES_CONFIG` skip predicate. |

Run tests: `.venv/bin/python -m pytest test/ -q --ignore=test/test_modules`
(excludes `test/test_modules`, which makes a real Admin API call at import).
