"""Machine-wide scheduler ownership shared with older embedded-scheduler builds.

Only the dedicated worker claims the existing exclusive loopback port. New
web processes never acquire it or wait for takeover. The OS releases the
socket on process exit; graceful shutdown releases it after jobs finish.
The legacy takeover helper remains for compatibility with external callers.
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


def release_leadership():
    """Release only after all jobs stopped; normal process exit also frees the lock."""
    global _leader_socket
    with _lock:
        if _leader_socket is not None:
            _leader_socket.close()
            _leader_socket = None
