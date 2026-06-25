# Self-refreshing `oauth_token` — caveats explained with code, + an mtime-cached `load_config`

> Companion to `OAUTH_LAZY_TOKEN_PROPERTY_DESIGN.md`. Two questions:
> 1. The two "make-or-break" caveats, shown concretely in code.
> 2. Can we skip reloading `config.json` when its modified-time is unchanged, to kill the per-call overhead?

---

## Caveat A — reading `oauth_token` for *truthiness* must NOT trigger a refresh

### The problem, concretely

If `oauth_token` becomes a property that refreshes-on-read, then **any** access triggers it —
including the places that read it only to *classify* a config, none of which want network I/O.
Here are the exact current sites (all offline paths):

```python
# cloudinary_cli/utils/config_utils.py:283  — runs at the GROUP level, on every command
def is_valid_cloudinary_config():
    if cloudinary.config().cloud_name and cloudinary.config().oauth_token:   # <-- truthiness read
        return True
    return None not in [cloudinary.config().cloud_name,
                        cloudinary.config().api_key, cloudinary.config().api_secret]

# cloudinary_cli/utils/config_listing.py:76, 97, 109  — `config -ls`, fully offline
"type": "oauth" if config_obj.oauth_token else "api_key",
"type": "oauth" if active.oauth_token   else "api_key",
"type": "oauth" if env_config.oauth_token else "api_key",

# cloudinary_cli/core/config.py:191  — `config` header, offline
type_label = "oauth" if active.oauth_token else "api_key"
```

A property can't distinguish "are you OAuth?" from "give me a token to send." So a naive property
turns `cld config -ls` — which should be 100% offline — into something that refreshes every stale
saved token just to print a table. **That is the exact Finding-1 hang we removed**, reintroduced.

### The fix: split *presence* from *value*

Keep a non-refreshing way to ask "is this OAuth / is a token present," and let only the **value**
read on the request path refresh. Two private fields back the public property:

```python
# cloudinary_cli/auth/oauth_config.py  (new)
import cloudinary
from cloudinary_cli.auth import refresh_url_if_stale
from cloudinary_cli.auth.session import from_cloudinary_url

class OAuthConfig(cloudinary.Config):
    """A Config whose oauth_token refreshes itself on read for the request path, while presence/
    type checks read the raw stored token and never touch the network."""

    def bind_saved(self, name, url):
        # association the resolver used to keep in a module global — now lives on the object
        self._saved_name = name
        self._raw_oauth_token = from_cloudinary_url(url).access_token
        self._oauth_url = url

    # --- presence: cheap, no network. Use THIS in type/validity checks. ---
    @property
    def has_oauth(self):
        return bool(getattr(self, "_raw_oauth_token", None))

    # --- value: refresh-if-stale, used by the SDK on the request path. ---
    @property
    def oauth_token(self):
        name = getattr(self, "_saved_name", None)
        if name is None:
            # env / -c / api-key config: serve the static value, never refresh
            return getattr(self, "_raw_oauth_token", None)
        fresh_url = refresh_url_if_stale(name, self._oauth_url)   # existing lock+double-check+persist
        if fresh_url != self._oauth_url:
            self._oauth_url = fresh_url
            self._raw_oauth_token = from_cloudinary_url(fresh_url).access_token
        return self._raw_oauth_token
```

Then repoint the offline checks at `has_oauth` (presence), not `oauth_token` (value):

```python
# is_valid_cloudinary_config
cfg = cloudinary.config()
if cfg.cloud_name and getattr(cfg, "has_oauth", False):          # no refresh
    return True

# config_listing / core.config type labels
"type": "oauth" if getattr(config_obj, "has_oauth", False) else "api_key"
```

> Note the property must be a **data descriptor on the class** (a `property` is). The SDK's
> `__getattr__` (`return self.__dict__.get(i)`) only fires for *missing* attributes; the token is in
> `__dict__`, so `__getattr__` never sees it — but a class-level `property` *overrides* `__dict__` on
> read. That's why this works where a `__getattr__` hook wouldn't.

### Subtlety: `config_to_dict` enumerates `__dict__`

```python
# config_utils.py:97
def config_to_dict(config):
    return {k: v for k, v in config.__dict__.items() if not k.startswith("_")}
```

A `property` lives on the class, not in `__dict__`, so `config_to_dict` would **lose** `oauth_token`
from the masked/JSON views. Fix: have the masking layer read the raw token explicitly, e.g. add it
back from `_raw_oauth_token`, or store the raw token under the public key `oauth_token` in `__dict__`
*and* let the property shadow it on read (a property shadows the instance dict on attribute access,
but `__dict__["oauth_token"]` is still there for `config_to_dict` to enumerate). The cleanest: keep
`oauth_token` in `__dict__` for serialization, and have the property's getter read/refresh from it.

---

## Caveat B — refreshing inside the getter must not `reset_config()` or deadlock

### The problem, concretely

Today refresh goes through `refresh_cloudinary_config`:

```python
# config_utils.py
def refresh_cloudinary_config(cloudinary_url):
    cloudinary.reset_config()                       # <-- clears the global singleton
    cloudinary.config()._load_from_url(cloudinary_url)
```

If the **getter** for `oauth_token` called this, then reading `config().oauth_token` would, mid-read,
`reset_config()` — destroying the very object whose property is executing, and replacing our
`OAuthConfig` with a plain `Config` (property gone). It also opens the reset-then-reload window where
a concurrent worker thread reads a half-cleared global. And `refresh_url_if_stale` → `update_config`
takes the reentrant `config_lock`; doing a global swap underneath that is the fragile part.

### The fix: refresh in place, never swap the global from inside the getter

The getter (above) only mutates its **own** `_oauth_url` / `_raw_oauth_token` and lets
`refresh_url_if_stale` handle the **persist** (atomic write under the lock — already correct,
single-flight across threads and processes). No `reset_config()`, no global swap, no half-cleared
window. The lock is reentrant, so the getter running inside an in-progress operation that already
holds it won't deadlock.

The one place that legitimately swaps the global is the **resolver** (Phase A), once per process —
that's where `OAuthConfig(...).bind_saved(name, url)` gets installed as `cloudinary._config`. Audit
every `reset_config()` call so a saved OAuth login always ends up installed as `OAuthConfig`, never a
plain `Config` (else the property silently disappears — the #1 risk from the design doc).

---

## The mtime cache — yes, and it's the cleaner overhead fix

Your instinct is good: most `load_config()` calls re-read and re-parse an unchanged file. Cache the
parsed dict keyed on the file's `(mtime, size)`; reload only when it changes. Current code:

```python
# config_utils.py:32
def load_config():
    return read_json_from_file(CLOUDINARY_CLI_CONFIG_FILE, does_not_exist_ok=True)
```

Cached version:

```python
import os

_config_cache = None
_config_cache_stat = None   # (st_mtime_ns, st_size)

def _config_stat():
    try:
        st = os.stat(CLOUDINARY_CLI_CONFIG_FILE)
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return None

def load_config():
    global _config_cache, _config_cache_stat
    stat = _config_stat()
    if stat is not None and stat == _config_cache_stat and _config_cache is not None:
        return _config_cache                       # unchanged file: skip read + JSON parse
    cfg = read_json_from_file(CLOUDINARY_CLI_CONFIG_FILE, does_not_exist_ok=True)
    _config_cache, _config_cache_stat = cfg, stat
    return cfg
```

And invalidate on our own writes so a writer sees its own update immediately:

```python
def save_config(config):
    global _config_cache, _config_cache_stat
    _verify_file_path(CLOUDINARY_CLI_CONFIG_FILE)
    write_json_to_file(config, CLOUDINARY_CLI_CONFIG_FILE, atomic=True)
    _restrict_permissions(CLOUDINARY_CLI_CONFIG_FILE)
    _config_cache = None            # force re-stat/reload next load_config()
    _config_cache_stat = None
```

### Caveats on the cache (important)

1. **mtime granularity.** Use `st_mtime_ns` (nanosecond) + `st_size`, not 1-second `st_mtime`. A
   sub-second refresh-then-read on a coarse FS could otherwise miss a change. The `os.replace` in
   `atomic_write` updates mtime, so cross-process changes are detected.
2. **Return a copy if callers mutate.** Several callers do `cfg = load_config(); cfg.update(...)`.
   If they mutate the returned dict in place they'd corrupt the shared cache. Either return
   `dict(cfg)` (cheap; safest) or audit that mutators always go through `update_config`
   (which builds on `load_config` then `save_config`). Returning a shallow copy is the safe default.
3. **It does NOT remove the need to read under the lock for refresh.** The
   read-modify-write in `refresh_url_if_stale`/`update_config` must still `load_config()` *inside*
   the lock to re-check freshness — the cache is fine there too (it re-stats; if a peer just wrote,
   mtime changed, it reloads). The cache only saves the *redundant* reads, not the correctness read.
4. **Still mostly moot if we adopt the property.** With the self-refreshing `oauth_token`, the
   per-call `load_config()` in `ensure_active_config_fresh` disappears entirely. The mtime cache is
   still worth having (other hot reads: `is_valid_cloudinary_config` at group level, refresh loops),
   but it's a complementary optimization, not the primary fix.

### Recommendation on overhead

- **Primary:** the property approach removes the per-API-call `load_config()` on the hot path
  outright (no more `ensure_active_config_fresh`).
- **Secondary:** add the mtime+size cache to `load_config()` (with copy-on-return) so the remaining
  reads — group-level validity check, `-ls`, refresh sweeps — stop re-parsing an unchanged file.

Together they take the steady-state per-request config overhead from "disk read + JSON parse +
URL parse, every call, every thread" down to "one `os.stat`, and a token refresh only when the
5-minute token has actually expired."
