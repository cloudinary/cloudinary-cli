# Design: self-refreshing `oauth_token` — collapse the scattered refresh hooks

> Proposal under evaluation: make the SDK config's `oauth_token` resolve through a callable/property
> that refreshes a stale token on read, so we can delete `ensure_active_config_fresh` and every
> chokepoint call (`call_api`, `execute_single_request`, `query_cld_folder`, `cld_folder_exists`).
> Context: access tokens are valid ~5 minutes, so refreshes are frequent and expected.
>
> Verdict: **the idea is sound and the SDK seam exists, but a plain `__getattr__` hook will NOT
> work** because of how the SDK stores the token. A `property`/descriptor approach works, with two
> caveats that must be handled. Details below, traced against the installed SDK.

---

## 1. Why this is the right instinct

Every place that needs auth reads the token the same way, at call time:

```python
# cloudinary/api_client/call_api.py:63
oauth_token = options.pop("oauth_token", cloudinary.config().oauth_token)
# cloudinary/uploader.py:877
oauth_token = options.get("oauth_token", cloudinary.config().oauth_token)
```

Both read **`cloudinary.config().oauth_token`** at the moment of the request. That is a single,
universal seam. If reading that attribute returns a *fresh* token, then:

- `ensure_active_config_fresh()` and all four chokepoint calls can be **deleted**.
- Search's direct `.execute()` paths, sync's threaded `call_api`, provisioning, and any future API
  entry point all get correct tokens for free — no hand-maintained chokepoint list.
- The "stale token mid-bulk-run → 401" gap closes, because the token is re-evaluated per request.

This directly answers the 5-minute-validity reality: refresh becomes demand-driven at the exact
point of use, once per request, with no proactive probing.

---

## 2. The blocker: the SDK does NOT route `oauth_token` through `__getattr__`

`cloudinary.Config` (BaseConfig):

```python
def __getattr__(self, i):
    return self.__dict__.get(i)
```

`__getattr__` fires **only when the attribute is absent from the instance `__dict__`.** But the
token is written *into* `__dict__`:

```python
def _setup_from_parsed_url(self, parsed_url):
    ...
    self.__dict__[k] = v[0]          # oauth_token lands here
```

So `config().oauth_token` is a normal dict hit and `__getattr__` never runs. **A `__getattr__`-based
hook is dead on arrival.** This is the trap to avoid.

### What does work

A **data descriptor** (a `property`) defined on the *class* takes precedence over the instance
`__dict__`, so it intercepts the read even when `oauth_token` is also in `__dict__`. Options, in
order of preference:

1. **Subclass + property (cleanest, CLI-local, no SDK fork).** Define a `Config` subclass with an
   `oauth_token` property whose getter refreshes-if-stale and returns the live access token; the
   raw stored URL/refresh-token live in private attributes. Install it as `cloudinary._config` (the
   object `cloudinary.config()` returns). The SDK's `config().oauth_token` then hits our property.
   - Requires confirming the SDK lets us swap the config singleton (it stores a module-level
     `_config`; `reset_config()` rebuilds it — see §4 risk).

2. **Store the token outside `__dict__` so the existing `__getattr__` fires.** Pop `oauth_token`
   out of `__dict__` and serve it from `__getattr__`. Fragile: anything that writes
   `config().oauth_token = x` (or `update(oauth_token=...)`) puts it back in `__dict__` and silently
   disables the hook. Not recommended.

3. **Monkeypatch `BaseConfig.oauth_token` as a property at CLI import.** Works (class-level data
   descriptor), but mutates SDK global state for the whole process — affects every Config instance,
   including the env-derived `cloudinary.Config()` we build in `config_listing`. Has to no-op for
   non-OAuth / non-CLI-managed configs. Workable but the broadest blast radius.

**Recommendation: option 1** (subclass + property installed as the active config).

---

## 3. Two semantic caveats that MUST be handled

### Caveat A — `oauth_token` is read for *truthiness*, not just for the value

The CLI itself does this in several places:

```python
"type": "oauth" if config_obj.oauth_token else "api_key"   # config_listing.py x3, core/config.py
if cloudinary.config().cloud_name and cloudinary.config().oauth_token:  # is_valid_cloudinary_config
```

If `oauth_token` becomes a refresh-on-read property, then **a type check or a validity check would
trigger a network refresh** — exactly the kind of accidental I/O on an offline path (`config -ls`,
`config -s`, `is_valid_cloudinary_config` at the group level) that this whole effort was trying to
remove (the original Finding 1 hang). This is the subtle regression risk.

Mitigations:
- The property getter must **refresh only when the caller actually needs a live token for a
  request** — but a property can't tell "truthiness check" from "real use." So: keep a separate,
  non-refreshing attribute for *presence* (e.g. an `is_oauth` flag or a raw `_oauth_token_raw`) and
  point the type/validity checks at *that*, leaving the refreshing `oauth_token` only on the
  request path. i.e. the property refreshes; the CLI's own introspection reads the raw field.
- Or gate the getter: refresh only if `expires_at` is set AND we're not in a "describe" context.
  Context flags are ugly; prefer the separate-presence-field approach.

### Caveat B — reentrancy and thread safety on read

A 5-minute token under a multi-threaded sync means many threads may read `oauth_token` near
expiry simultaneously. The getter must reuse the **existing** lock + double-check from
`refresh_url_if_stale` (which is already correct and single-flight across threads and processes —
preserve it verbatim). The getter also must not deadlock: it runs *inside* SDK request code, and
`refresh_url_if_stale` → `update_config` takes the reentrant `config_lock` and then calls
`refresh_cloudinary_config` (which does `reset_config()` + reload of the **global**). Rebuilding the
global config object *from within a getter on that same global* is the dangerous part:

- Do **not** `reset_config()` inside the getter. Instead, refresh, persist, and update only the
  private token fields on the *current* object (no global swap). The getter returns the new access
  token; no `cloudinary.reset_config()` on the hot path. This also fixes the latent
  reset-then-reload thread race documented in the concurrency review.

---

## 4. Other risks / unknowns to confirm before building

1. **`reset_config()` rebuilds the singleton.** The SDK's `reset_config()` constructs a fresh
   `Config()`. If we installed a subclass instance, any code path that calls `reset_config()` (we do,
   in `refresh_cloudinary_config`, and the SDK may internally) would replace our self-refreshing
   object with a plain one, silently disabling the property. Audit every `reset_config()` call and
   route config installation through one helper that always installs the subclass.

2. **Env / `-c` configs.** Env-derived and inline-`-c` OAuth URLs currently never refresh (no saved
   entry, no refresh token persisted). The property must no-op for configs with no refresh token
   (return the static token) — same as `refresh_url_if_stale`'s existing early-out.

3. **Persistence on rotation.** When the getter refreshes, it must still write the rotated token back
   to `config.json` under the lock (so the next *process* benefits and the single-use token isn't
   re-burned). That write must use the existing atomic `update_config`. The getter therefore still
   needs to know *which saved name* it maps to — i.e. it needs the `_active_name` association, just
   carried on the config object instead of a module global. (This is strictly better: the binding
   lives with the object, not in resolver module state.)

4. **`config_to_dict` / masking.** `config_to_dict` iterates `__dict__`; a property is on the class,
   not in `__dict__`, so the masking/listing code that enumerates `__dict__` would **miss**
   `oauth_token` unless the raw value is still stored as an instance attr. Keep the raw token in
   `__dict__` (under a private name) so masking still sees it; expose the live one via the property.

5. **SDK upgrades.** This couples us to two SDK internals: `config().oauth_token` being read per
   request (stable, it's the documented OAuth path) and the descriptor-vs-`__dict__` precedence
   (Python language guarantee, safe). The fragile coupling is `reset_config()` behavior (#1).

---

## 5. What gets deleted if this lands

- `config_resolver.ensure_active_config_fresh` (whole function).
- The 4 call sites: `api_utils.call_api`, `api_utils.query_cld_folder`, `api_utils.cld_folder_exists`,
  `core/search.execute_single_request`.
- The module-global `_active_name` *as a refresh input* (still useful for `config -ls` "active"
  marker — keep it, or move the active-name onto the config object too).
- The per-call `load_config()` on the hot path.

What stays (and should be reused verbatim inside the getter):
- `refresh_url_if_stale`'s lock + double-check + atomic persist (the genuinely-correct core).
- The resolver's Phase-A selection/precedence and the offline format check.

---

## 6. Recommended shape

1. Add a CLI `OAuthConfig(cloudinary.Config)` subclass:
   - stores `_raw_url` / `_saved_name` (the saved-config association),
   - `oauth_token` is a **property**: if a saved OAuth token, refresh-if-stale (reusing
     `refresh_url_if_stale`'s lock/double-check/persist), update the in-object token in place (no
     `reset_config`), return the live access token; otherwise return the static stored value,
   - keeps the raw token in `__dict__` under a private key for masking/introspection.
2. Route all config installation (resolver, `refresh_cloudinary_config`) through one helper that
   installs this subclass and never leaves a plain `Config` as the active global for a saved OAuth
   login. Audit `reset_config()`.
3. Point **presence/type/validity** checks (`is_valid_cloudinary_config`, the three
   `"oauth" if ... else "api_key"` sites) at the **raw** field / an `is_oauth` flag — NOT the
   refreshing property — so offline `config`/`-ls`/`-s` never touch the network (preserves the
   Finding-1 fix).
4. Delete `ensure_active_config_fresh` and its four call sites.
5. Tests: (a) reading `oauth_token` on a stale saved config refreshes once and persists; (b) reading
   it on a fresh / api-key / env config does no network; (c) `config -ls` / `-s` /
   `is_valid_cloudinary_config` do **zero** network even with a stale token (regression guard for
   Caveat A); (d) concurrent threaded reads single-flight (one refresh, others adopt).

This collapses the scattered hooks into one well-placed seam, fixes the mid-run-401 and the
reset-then-reload race, and keeps the offline paths offline — provided Caveat A (truthiness reads)
and the `reset_config` audit (#1/#4) are handled. Those two are the make-or-break items.
