"""Tiny per-instance memoization with a time-based expiry.

Used to avoid re-running an expensive per-request computation (a full
cache-table scan + Python join, see app/services/ran/*.py) on every
dashboard request when the underlying SQLite cache table only changes once
per background sync cycle (300s+).

Deliberately not Flask-Caching's cache.memoize(): that needs a bound Flask
app (current_app), which would force every direct-instantiation unit test
for these services (see tests/test_ran_*.py — fake repos, no app context)
to run inside app.app_context() just to call a getter method. Storing the
cached value on the instance itself (not a shared module-level dict) also
means distinct instances never share state, so it's still safe with
short-lived instances like the ones those tests create.
"""
import time
from functools import wraps


def ttl_cache(seconds):
    def decorator(fn):
        attr = f"_ttl_cache_{fn.__name__}"

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            now = time.monotonic()
            cached = getattr(self, attr, None)
            if cached is not None:
                cached_at, cached_args, cached_kwargs, value = cached
                if now - cached_at < seconds and cached_args == args and cached_kwargs == kwargs:
                    return value
            value = fn(self, *args, **kwargs)
            setattr(self, attr, (now, args, kwargs, value))
            return value

        return wrapper

    return decorator
