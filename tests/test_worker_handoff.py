"""Cross-folder handoff must drain the old worker and preserve saved data."""
from contextlib import nullcontext
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from app.services import worker_handoff as handoff


def project(path):
    (path / 'app').mkdir(parents=True)
    (path / 'app' / '__init__.py').touch()
    (path / 'app' / 'worker_runtime.py').touch()
    (path / 'worker.py').touch()
    (path / 'run.py').touch()
    (path / 'instance').mkdir()
    return path


def owner(root, pid=41, script='worker.py', extra=()):
    return {'pid': pid, 'command_line': subprocess.list2cmdline([sys.executable, str(root / script), *extra])}


@pytest.fixture
def roots(tmp_path):
    return project(tmp_path / 'old version'), project(tmp_path / 'new version')


def configure(monkeypatch, previous, status=None):
    state = {'busy': True, 'stops': []}
    monkeypatch.setattr(handoff, 'port_is_available', lambda: not state['busy'])
    monkeypatch.setattr(handoff, 'read_lock_owner', lambda: owner(previous))
    monkeypatch.setattr(handoff, 'read_worker_status', lambda path: status or {
        'pid': 41, 'healthy': True, 'heartbeat_age_seconds': 1, 'state': 'running'})

    def stop(path):
        state['stops'].append(Path(path))
        state['busy'] = False
        return True

    monkeypatch.setattr(handoff, 'request_worker_stop', stop)
    return state


def test_no_owner_allows_new_worker_without_reading_copied_heartbeat(monkeypatch, roots):
    monkeypatch.setattr(handoff, 'port_is_available', lambda: True)
    monkeypatch.setattr(handoff, 'read_worker_status', lambda path: pytest.fail('Copied status was trusted'))
    assert handoff.prepare_worker_start(roots[1]) is False


def test_cross_folder_handoff_targets_old_instance_and_not_new_copy(monkeypatch, roots):
    old, new = roots
    state = configure(monkeypatch, old)
    seen = []

    def status(path):
        seen.append(Path(path))
        assert Path(path) == old / 'instance'
        return {'pid': 41, 'healthy': True, 'heartbeat_age_seconds': 1, 'state': 'running'}

    monkeypatch.setattr(handoff, 'read_worker_status', status)
    assert handoff.prepare_worker_start(new) is False
    assert state['stops'] == [old / 'instance']
    assert seen


def test_healthy_current_worker_is_reused(monkeypatch, roots):
    state = configure(monkeypatch, roots[1])
    assert handoff.prepare_worker_start(roots[1]) is True
    assert state['stops'] == []


def test_unhealthy_current_worker_is_gracefully_replaced(monkeypatch, roots):
    state = configure(monkeypatch, roots[1], {'pid': 41, 'healthy': False, 'heartbeat_age_seconds': 1})
    assert handoff.prepare_worker_start(roots[1]) is False
    assert state['stops'] == [roots[1] / 'instance']


def test_quoted_project_path_and_custom_instance_are_resolved(roots, tmp_path):
    instance = tmp_path / 'custom data'
    result = handoff.worker_location(owner(roots[0], extra=('--instance-path', str(instance))))
    assert result == (roots[0], instance)


@pytest.mark.parametrize('command', ['unrelated.exe worker.py', 'python.exe -c "print(1)"', 'python.exe worker.py'])
def test_unrecognized_owner_is_left_running(monkeypatch, roots, command):
    state = configure(monkeypatch, roots[0])
    monkeypatch.setattr(handoff, 'read_lock_owner', lambda: {'pid': 41, 'command_line': command})
    with pytest.raises(handoff.WorkerHandoffError):
        handoff.prepare_worker_start(roots[1])
    assert state['stops'] == []


def test_legacy_embedded_scheduler_requires_manual_stop(monkeypatch, roots):
    state = configure(monkeypatch, roots[0])
    monkeypatch.setattr(handoff, 'read_lock_owner', lambda: owner(roots[0], script='run.py'))
    with pytest.raises(handoff.WorkerHandoffError, match='embedded scheduler'):
        handoff.prepare_worker_start(roots[1])
    assert state['stops'] == []


def test_mismatched_heartbeat_never_receives_stop_request(monkeypatch, roots):
    state = configure(monkeypatch, roots[0], {'pid': 99, 'healthy': True, 'heartbeat_age_seconds': 1})
    monkeypatch.setattr(handoff, 'STATUS_TIMEOUT', 0)
    with pytest.raises(handoff.WorkerHandoffError, match='heartbeat'):
        handoff.prepare_worker_start(roots[1])
    assert state['stops'] == []


def test_waiting_for_inflight_work_does_not_force_stop(monkeypatch, roots):
    state = configure(monkeypatch, roots[0])
    monkeypatch.setattr(handoff, 'request_worker_stop', lambda path: True)
    monkeypatch.setattr(handoff, 'HANDOFF_TIMEOUT', 0)
    with pytest.raises(handoff.WorkerHandoffError, match='still finishing'):
        handoff.prepare_worker_start(roots[1])
    assert state['busy'] is True


def test_launcher_only_accepts_its_own_new_worker_pid(tmp_path, monkeypatch):
    from scripts import ensure_sync_worker as launcher

    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(handoff, 'is_launched_worker', lambda pid, launcher_pid: pid == launcher_pid)
    process = SimpleNamespace(pid=55, returncode=1, poll=lambda: 1)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *args, **kwargs: process)
    assert launcher.start_worker(lambda path: {'healthy': True, 'pid': 44}) == 1


def test_launcher_accepts_matching_pid_and_records_startup_errors(tmp_path, monkeypatch):
    from scripts import ensure_sync_worker as launcher

    monkeypatch.setattr(launcher, 'ROOT', tmp_path)

    def spawn(*args, **kwargs):
        kwargs['stderr'].write(b'Test startup diagnostic\n')
        kwargs['stderr'].flush()
        return SimpleNamespace(pid=55, returncode=None, poll=lambda: None)

    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    assert launcher.start_worker(lambda path: {'healthy': True, 'pid': 55}) == 0
    assert b'Test startup diagnostic' in (tmp_path / 'logs' / 'worker-startup.log').read_bytes()


def test_launcher_serializes_handoff_before_spawning(monkeypatch):
    from scripts import ensure_sync_worker as launcher

    events = []
    monkeypatch.setattr(handoff, 'worker_startup_lock', nullcontext)
    monkeypatch.setattr(handoff, 'prepare_worker_start', lambda root: events.append('handoff') or False)
    monkeypatch.setattr(launcher, 'start_worker', lambda reader: events.append('start') or 0)
    assert launcher.main() == 0
    assert events == ['handoff', 'start']


def test_real_old_worker_finishes_work_before_port_is_reused(monkeypatch, roots):
    old, new = roots
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    (old / 'instance' / 'saved-data.db').write_bytes(b'saved-data-sentinel')
    script = r"""import json, os, socket, sys, time
from pathlib import Path
from datetime import datetime, timezone
root=Path(__file__).resolve().parent
instance=root/'instance'
started=datetime.now(timezone.utc).isoformat()
status={'pid':os.getpid(),'started_at':started,'heartbeat_at':started,'state':'running','jobs':{'test':{'thread_alive':True}}}
with socket.socket() as lock:
    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'): lock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    lock.bind(('127.0.0.1',int(sys.argv[1])))
    lock.listen(1)
    (instance/'sync-worker-status.json').write_text(json.dumps(status))
    while True:
        try:
            request=json.loads((instance/'sync-worker-stop.json').read_text())
            if request.get('pid')==os.getpid() and request.get('started_at')==started: break
        except (OSError,ValueError): pass
        time.sleep(.05)
    time.sleep(.2)
    (instance/'inflight-finished').touch()
"""
    (old / 'worker.py').write_text(script)
    process = subprocess.Popen([sys.executable, str(old / 'worker.py'), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (old / 'instance' / 'sync-worker-status.json').exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(.05)
        monkeypatch.setattr(handoff, '_LOCK_PORT', port)
        actual_pid = json.loads((old / 'instance' / 'sync-worker-status.json').read_text())['pid']
        assert handoff.is_launched_worker(actual_pid, process.pid)
        monkeypatch.setattr(handoff, 'read_lock_owner', lambda: owner(old, actual_pid))
        assert handoff.prepare_worker_start(new) is False
        assert process.wait(timeout=5) == 0
        assert (old / 'instance' / 'inflight-finished').exists()
        assert (old / 'instance' / 'saved-data.db').read_bytes() == b'saved-data-sentinel'
        with socket.socket() as replacement:
            replacement.bind(('127.0.0.1', port))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_shutdown_stops_only_current_project(monkeypatch, roots):
    state = configure(monkeypatch, roots[1])
    monkeypatch.setattr(handoff, 'worker_startup_lock', nullcontext)
    assert handoff.stop_current_worker(roots[1]) is True
    assert state['stops'] == [roots[1] / 'instance']


def test_shutdown_leaves_another_project_running(monkeypatch, roots):
    state = configure(monkeypatch, roots[1])
    monkeypatch.setattr(handoff, 'worker_startup_lock', nullcontext)
    assert handoff.stop_current_worker(roots[0]) is True
    assert state['stops'] == []


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows mutex')
def test_concurrent_launchers_are_serialized(monkeypatch):
    import threading
    import uuid

    monkeypatch.setattr(handoff, 'STARTUP_MUTEX_NAME', 'Global\\NocDashboardTest-' + uuid.uuid4().hex)
    attempted = threading.Event()
    entered = threading.Event()
    errors = []

    def second_launcher():
        attempted.set()
        try:
            with handoff.worker_startup_lock():
                entered.set()
        except Exception as error:
            errors.append(error)

    with handoff.worker_startup_lock():
        thread = threading.Thread(target=second_launcher, daemon=True)
        thread.start()
        assert attempted.wait(2)
        assert not entered.wait(.1)
    thread.join(5)
    assert entered.is_set()
    assert not errors
    assert not thread.is_alive()
