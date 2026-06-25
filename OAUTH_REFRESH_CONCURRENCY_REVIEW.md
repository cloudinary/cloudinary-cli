# OAuth lazy-refresh concurrency review — `ensure_active_config_fresh`

> Scope: the lazy token-refresh design landed in `43fb67a` (`oauth-login` branch). Focuses on
> behavior under (1) high in-process + cross-process parallelism (sync / upload-dir with up to ~30
> `cld` instances) and (2) one long-running instance while a second instance mutates config
> (changing the default, dropping configs). Every claim below was traced against the code, not the
> design doc.

---

## 1. How refresh is wired today

`resolve_cli_config` (group callback, Phase A) does **no network**. It records the selected saved
config name in the module global `_active_name`. Then, at each API chokepoint, Phase B runs:

```python
# config_resolver.ensure_active_config_fresh()
name = _active_name
if name is None: return
url = load_config().get(name)          # disk read
if url is None: return
fresh = refresh_url_if_stale(name, url) # may take config_lock + network
if fresh != url:
    refresh_cloudinary_config(fresh)    # mutates the SDK *process global*
```

`refresh_url_if_stale` (auth/__init__.py):

```python
if not is_oauth_url(url): return url
session = from_cloudinary_url(url)
if (session.is_fresh() and not force) or not session.refresh_token:
    return url                          # FAST PATH: no lock, no I/O beyond the load_config above
with config_lock():                     # FileLock on config.json.lock (cross-process, reentrant)
    url = load_config().get(name, url)  # re-read under lock
    session = from_cloudinary_url(url)
    if (session.is_fresh() and not force) or not session.refresh_token:
        return url                      # peer already refreshed -> adopt, don't burn
    token_response = flow.refresh(...)  # NETWORK, single-use refresh token
    update_config({name: refreshed_url})# atomic write (tmp + os.replace), reentrant lock
    return refreshed_url
```

Chokepoints calling `ensure_active_config_fresh`:

| Site | Frequency |
|---|---|
| `api_utils.call_api` | **once per API call** — and `upload_file` → `call_api`, run under `run_tasks_concurrently` (N worker threads) |
| `core/search.py::execute_single_request` | once per search request |
| `api_utils.query_cld_folder` | once per folder query (before the cursor loop — good) |
| `api_utils.cld_folder_exists` | once per existence check |

Freshness: `is_fresh()` = `expires_at - 30s > now` (`OAUTH_EXPIRY_SKEW_SECONDS = 30`).

---

## 2. The user's concern #1 — "30 instances all refresh at once"

### 2.1 What actually happens — it is mostly safe, but the design is wasteful and fragile

**The good news (correctness):** the refresh itself is *not* a correctness problem under
concurrency. The lock + double-check makes the actual refresh single-flight:

- Only one process at a time holds `config_lock()`. The first to enter refreshes, rotates the
  single-use token, and `os.replace`s the file atomically. Every other process, on acquiring the
  lock, re-reads and sees a now-fresh token → adopts it → **does not** burn a second refresh.
- So we will **not** stampede the OAuth server with 30 concurrent refreshes for the same config,
  and we will **not** burn 30 refresh tokens. That part of the design is sound.

**The bad news (this is the poor design you flagged):**

1. **Per-call fast-path cost, multiplied by every asset and every thread.** `ensure_active_config_fresh`
   runs on **every** `call_api`. For a fresh token the cost is `load_config()` (a disk read +
   JSON parse) **plus** `from_cloudinary_url` parse, on every single upload/admin call. In a sync
   of 50k assets across N threads that is 50k×(disk read + parse) of `config.json`, on the hot
   path, purely to discover "still fresh, nothing to do." It is not a hang, but it is real,
   repeated, avoidable I/O and lock-adjacent work in the tightest loop the CLI has.

2. **In-process thread contention on a reentrant lock is invisible but real.** `run_tasks_concurrently`
   spins up worker threads; each calls `call_api` → `ensure_active_config_fresh`. On the fast path
   they don't take `config_lock`, so threads mostly don't serialize there. **But** the moment the
   token actually goes stale mid-run (long sync crossing the `expires_at` boundary), *every* worker
   thread simultaneously fails `is_fresh()`, and they pile up on `config_lock()`. One refreshes; the
   rest serialize behind it, re-read, adopt. Correct, but a synchronized stall of all workers at the
   expiry boundary — and `refresh_cloudinary_config` mutates the **process-global** SDK config (see
   §2.2), which those same threads are concurrently reading.

3. **`refresh_cloudinary_config` mutates global SDK state while other threads make API calls.**
   This is the sharpest in-process hazard. `refresh_cloudinary_config` does
   `cloudinary.reset_config()` then `_load_from_url(...)`. There is a window where the global config
   has been reset but not yet reloaded. A peer worker thread issuing `uploader.upload` during that
   window can read a half-cleared global config. The cross-*process* path is safe (separate address
   spaces, atomic file); the cross-*thread* path within one process shares one mutable
   `cloudinary.config()` singleton with no lock around the reset+reload. This is a latent data race,
   not currently covered by any test.

4. **Cross-process thundering herd at the expiry boundary.** 30 processes started near the token's
   expiry will each independently hit the stale branch, then queue on the *file* lock one-by-one.
   The first refreshes (network); the other 29 each acquire the lock, re-read, see fresh, release.
   That is 29 serialized lock acquisitions + 29 `load_config` re-reads gated on a single
   cross-process `FileLock` — a serialization point that all 30 bulk jobs funnel through at the same
   instant. No token burn, but a real latency cliff and a single point of contention.

### 2.2 Summary of #1

- **Token burn / OAuth stampede:** safe. Single-flight via lock + double-check works across
  processes and threads.
- **Performance:** poor. Per-call `load_config` on the hot path; synchronized stall of all
  workers/processes at the expiry boundary; cross-process serialization on one file lock.
- **In-process thread safety of the SDK global:** **unsafe (latent race)** — `reset_config()` +
  reload is not atomic w.r.t. concurrent reader threads.

---

## 3. The user's concern #2 — long-running instance vs. a second instance mutating config

Scenario: instance A is mid-`sync` (minutes long). Instance B runs `cld config -d other`,
`cld config -rm A's-config`, `cld config -ud`, etc.

### 3.1 Default change (`-d` / `-ud`) — safe, ignored by A

Instance A resolved its config **once** at startup and cached the selection in its own process
global `_active_name`. A re-reads `config.json` in `ensure_active_config_fresh`, but only to fetch
**A's own** `_active_name` entry's URL — it never re-reads `__default__`. So B changing or clearing
the default has **zero effect** on a running A. Correct and desirable (A shouldn't switch accounts
mid-sync). ✔

### 3.2 Dropping the config A is using (`cld config -rm <A's config>`) — degrades, mostly safe

- B's `-rm` does `remove_config_keys` under `config_lock()` + atomic write. A's in-flight API calls
  are unaffected (A already loaded the URL into its SDK global at resolve time).
- The exposure is **only** inside `ensure_active_config_fresh`: `url = load_config().get(name)`. If
  B removed the entry, this returns `None` → A **returns early and does not refresh**. If A's token
  was about to expire, A then proceeds with a stale token and the next real API call fails with a
  401 — mid-sync, not a clean error. So: no crash, no corruption, but a removed-out-from-under-you
  config can turn a refresh into a silent skip → late 401.
- If A is the default and B removes A's config, `core/config.py` clears `__default__` too — fine,
  doesn't affect running A.

### 3.3 Token rotation interleaving (A refreshes while B refreshes/edits) — safe

Both go through `config_lock()` + atomic `os.replace`. No torn reads (atomic write guarantees a
reader sees either the old or the new whole file). The reentrant lock means A's
`refresh_url_if_stale` → `update_config` nests safely. ✔

### 3.4 The one real cross-process correctness gap — lost update on unrelated keys

`update_config` is read-modify-write under the lock:

```python
with config_lock():
    curr = load_config(); curr.update(new_config); save_config(curr)
```

Because every writer takes the lock, two writers don't lose each other's updates. **However**,
`set_default_config`, `clear_default_config`, `refresh` and `-rm` are *separate* lock acquisitions,
not one transaction. A multi-step CLI operation that does read-decide-write across two lock scopes
(e.g. `_should_auto_default` reads outside the lock, then `set_default_config` writes inside a new
lock) can interleave with a peer between the two scopes. Concretely: `login` does
`update_config({name: url})` (lock #1), then `_should_auto_default` does `load_config()` (no lock),
then `set_default_config` (lock #2). A peer running `cld config -d X` between #1 and #2 can have its
default silently overwritten by the auto-default, or vice-versa. Low probability, but it is a
genuine TOCTOU across separate lock scopes. ✔ data integrity (no torn file) / ✘ atomicity of the
logical operation.

### 3.5 Summary of #2

| B's action while A runs | A's outcome | Safe? |
|---|---|---|
| `-d` / `-ud` change default | ignored (A cached its selection) | ✔ |
| `-rm` A's config | refresh becomes a no-op → possible late 401 if token expires | ⚠ degraded |
| refresh / rotate token | atomic, single-flight, adopted | ✔ |
| concurrent multi-step config edit | file never torn; logical op can interleave (TOCTOU) | ⚠ |

---

## 4. Why `ensure_active_config_fresh` is the wrong shape

1. **Wrong altitude.** Freshness is a property of *the session we resolved*, but the check is
   re-derived from disk on every API call via a module global. It couples `api_utils` and
   `core/search` to resolver internals (`_active_name`) and to `load_config`.
2. **Hot-path I/O.** A `load_config()` (disk + JSON parse) per API call, inside the busiest loops,
   to almost always conclude "fresh."
3. **Process-global mutation under concurrency.** `refresh_cloudinary_config` resets the shared SDK
   singleton with no guard against concurrent reader threads (§2.2.3).
4. **Chokepoint set is hand-maintained.** Four call sites enumerated by hand; any new API entry
   point silently runs on a stale token. No test asserts completeness.
5. **Module-global `_active_name` is not thread-scoped.** Fine for one resolve per process, but it
   makes the whole mechanism implicitly single-config-per-process and invisible to readers.

---

## 5. Suggested fixes (in priority order)

### Fix A — refresh ONCE, eagerly, after resolution; drop the per-call hook (recommended)

The original eager refresh hung offline commands. The real fix for *that* was to **only refresh
when about to do network work**, not to refresh on *every* call. Move the refresh to a single point:
right after `resolve_cli_config` succeeds **and** the command is known to be a network command
(or lazily, but **once**, guarded by a process-level "already ensured" flag).

```python
_ensured = False
def ensure_active_config_fresh():
    global _ensured
    if _ensured or _active_name is None:
        return
    _ensured = True                     # one refresh attempt per process, not per call
    url = load_config().get(_active_name)
    ...
```

- Eliminates per-call `load_config` and per-call parse.
- Eliminates the synchronized all-threads stall at the expiry boundary (only the first call into
  any chokepoint pays the cost; the flag short-circuits the rest).
- A token expiring *mid-very-long-sync* is then handled by Fix C, not by re-checking every call.

### Fix B — make `refresh_cloudinary_config` atomic w.r.t. reader threads

Guard the `reset_config()` + `_load_from_url()` pair with a process-local `threading.Lock`, and have
the per-thread API path either hold it for the read or only ever swap in a fully-built config. The
cleanest version builds the new `cloudinary.Config` object off to the side and assigns it in one
reference swap rather than reset-then-mutate, so a reader thread never sees a half-cleared global.

### Fix C — refresh-on-401 retry, not refresh-on-every-call

The robust pattern for long-running multi-threaded/multi-process jobs is **reactive**: attempt the
API call; on a 401/auth error, take the lock, refresh once (double-checked), reload, and retry the
call exactly once. This:

- removes all proactive per-call freshness work,
- naturally single-flights across threads and processes (same lock + double-check already in place),
- correctly handles the token expiring mid-run and the "B removed my config" case (the retry can
  surface a clear "re-login" error instead of a raw 401).

Wrap it at `call_api` (which already catches exceptions) and at the two direct `.execute()` sites.

### Fix D — make logical config operations transactional

Provide a single `with config_lock(): read; mutate; write` helper for multi-step operations
(`login` + auto-default, refresh-and-default) so read-decide-write happens under **one** lock scope,
closing the §3.4 TOCTOU. At minimum, move `_should_auto_default`'s read and `set_default_config`'s
write into the same lock acquisition.

### Fix E — handle "config removed mid-run" explicitly

In the refresh path, distinguish "config gone" (`url is None` after the resolver had a name) from
"nothing to refresh," and surface a clear message (`config '<name>' was removed; please re-login`)
rather than silently skipping and letting a later 401 fall out.

### Fix F — assert chokepoint completeness

A test that monkeypatches the refresh entry point to a counter and exercises each top-level network
command, asserting it fired exactly once (pairs with Fix A's once-per-process flag).

---

## 6. Recommendation

Adopt **Fix A + Fix C** as the core redesign: resolve once, refresh once eagerly *or* reactively on
401, and stop probing the token on every call. Add **Fix B** to close the SDK-global thread race
(required before we trust multi-threaded sync under token rotation). **Fix D/E/F** are smaller
hardening steps. The current code is *correct on token burn* (the lock + double-check is genuinely
good and should be preserved verbatim inside whichever path survives), but the per-call hook and the
unguarded global mutation make it the wrong shape for the 30-instance / N-thread bulk workloads this
CLI is built for.
