"""Per-registry concurrency gates (ADR 0001).

Every registry rate-limits per client, so each one gets its own small gate: a scan
holds a slot only while it is actually talking to that registry, and the CPU-heavy
analysis afterwards runs outside any gate. A throttled npm therefore cannot starve
PyPI or git, and no host ever sees more than N of our requests at once.

Default is 5 per registry, overridable per registry:
    SCAN_GATE_NPM, SCAN_GATE_PYPI, SCAN_GATE_GIT, SCAN_GATE_MAVEN, SCAN_GATE_CONTAINER
"""
import os
import threading
import time
from contextlib import contextmanager

DEFAULT_SLOTS = 5
NAMES = ("npm", "pypi", "git", "maven", "container", "vulndb")

_gates = {}
_backoff_until = {}
_lock = threading.Lock()


def _slots(name: str) -> int:
    try:
        return max(1, int(os.environ.get(f"SCAN_GATE_{name.upper()}", DEFAULT_SLOTS)))
    except ValueError:
        return DEFAULT_SLOTS


def _gate(name: str) -> threading.BoundedSemaphore:
    with _lock:
        if name not in _gates:
            _gates[name] = threading.BoundedSemaphore(_slots(name))
        return _gates[name]


@contextmanager
def gate(name: str):
    """Hold one slot of this registry's gate. If the registry recently told us to
    slow down, wait out the back-off first (all lanes of that registry pause)."""
    g = _gate(name)
    g.acquire()
    try:
        with _lock:
            wait = _backoff_until.get(name, 0) - time.time()
        if wait > 0:
            time.sleep(wait)
        yield
    finally:
        g.release()


RATE_LIMIT_MARKERS = ("429", "too many requests", "rate limit", "rate-limit", "ratelimit", "secondary rate")


def looks_rate_limited(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in RATE_LIMIT_MARKERS)


def back_off(name: str, seconds: float = 30.0) -> None:
    """Pause this registry for everyone for a while."""
    with _lock:
        _backoff_until[name] = max(_backoff_until.get(name, 0), time.time() + seconds)
