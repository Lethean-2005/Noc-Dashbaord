"""Cross-process "only one of us actually syncs" lock.

The existing WERKZEUG_RUN_MAIN check in app/__init__.py only prevents the
Werkzeug debug reloader's own watcher/child pair from double-starting
background jobs *within one `python run.py` invocation*. It can't help
when something outside this app (an antivirus/EDR process-monitoring
agent, confirmed on this machine — even a bare unrelated `python -c` command
spawns an extra copy of itself here) launches a second, fully independent
`run.py` process: that process has its own memory, so it has no way of
knowing a first process already exists and already started every
scheduler.

This closes that gap without needing to know *why* the duplicate exists:
the first process to bind a fixed local TCP port becomes the "leader" and
starts every background job as normal; any other process that fails to
bind that same port (because the leader already holds it) is a "follower"
— it still serves HTTP requests normally, it just skips starting its own
duplicate set of schedulers. The bound socket is intentionally never
closed: as soon as the leader process exits for any reason, the OS
releases the port immediately, so a follower (or a fresh restart) can
become the new leader on its very next attempt — no stale-lock file to
clean up.

A follower that gave up once used to stay a follower forever, even if the
leader later disappeared — meaning every remaining process needed a manual
restart to get background sync running again. wait_for_leadership() below
fixes that: a follower keeps retrying in the background and automatically
takes over (starting its own schedulers) the moment the lock frees up.
"""
import socket
import threading
import time

# An arbitrary, unregistered high port used only as a lock — nothing ever
# connects to it, so the actual number doesn't matter as long as every
# process on this machine agrees on it.
_LOCK_PORT = 47913
_RETRY_SECONDS = 15

_leader_socket = None
_lock = threading.Lock()


def is_leader():
    """True if this process holds the lock (acquiring it on first call, or
    on a later call if a prior attempt failed — see wait_for_leadership()).
    Once a process is the leader, it stays the leader for its entire
    lifetime — this never gives up the socket to "check again" later."""
    global _leader_socket
    with _lock:
        if _leader_socket is not None:
            return True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_EXCLUSIVEADDRUSE (Windows-only) is the actual fix here: a bound
        # TCP socket that's never been put into listen() doesn't reliably
        # give exclusive ownership of the port on Windows the way a normal
        # bind() does on Unix — confirmed live, two separate processes both
        # had bind() succeed on the same port at the same time without it,
        # defeating the whole point of this lock. hasattr-guarded since the
        # constant doesn't exist in Python's socket module on non-Windows.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", _LOCK_PORT))
            sock.listen(1)
        except OSError:
            sock.close()
            return False
        _leader_socket = sock
        return True


def wait_for_leadership(on_acquired, retry_seconds=_RETRY_SECONDS):
    """For a process that's currently a follower: poll is_leader() every
    `retry_seconds` on a daemon thread, and call `on_acquired()` exactly
    once as soon as it succeeds — i.e. as soon as whichever process was
    the leader stops holding the port (crashed, was closed, restarted).
    Only call this once you've already confirmed is_leader() is False;
    it does not check whether this process is already the leader."""
    def _poll():
        while not is_leader():
            time.sleep(retry_seconds)
        on_acquired()

    threading.Thread(target=_poll, daemon=True, name="leader-lock-watcher").start()
