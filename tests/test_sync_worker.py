"""Dedicated worker regressions; no production queries or external sends."""
import json
import socket
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from app import create_app
from app.background import _BACKGROUND_JOBS, configured_jobs, start_worker_jobs
from app.services.scheduler_utils import join_scheduler_threads, start_singleton_loop
from app.worker_runtime import STATUS_NAME, WorkerAlreadyRunning, WorkerRuntime, read_worker_status


@pytest.fixture
def worker_app(tmp_path):
    app = Flask(__name__, instance_path=str(tmp_path))
    app.config.update(PROCESS_ROLE="worker", TIMEZONE="Asia/Phnom_Penh")
    yield app
    app.extensions.setdefault("scheduler_stop_event", threading.Event()).set()
    assert join_scheduler_threads(app, 3)
    runtime = app.extensions.get("sync_worker")
    if runtime is not None and runtime.owned:
        assert runtime.shutdown(timeout=3)


def test_web_app_starts_no_scheduler_or_leadership_watcher(tmp_path, monkeypatch):
    monkeypatch.setattr("app.worker_runtime.WorkerRuntime.acquire", lambda self: pytest.fail("web acquired worker lock"))
    monkeypatch.setattr("app.background.start_worker_jobs", lambda app: pytest.fail("web started jobs"))
    app = create_app("testing", instance_path=str(tmp_path))
    assert app.config["PROCESS_ROLE"] == "web"
    assert "sync_worker" not in app.extensions
    assert "scheduler_threads" not in app.extensions


def test_worker_factory_is_separate_from_debug_reloader(tmp_path, monkeypatch):
    from app.config import TestingConfig, config_map

    class WorkerTestConfig(TestingConfig):
        TESTING = False
        DEBUG = True

    monkeypatch.setitem(config_map, "worker_test", WorkerTestConfig)
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    monkeypatch.setattr("app.worker_runtime.is_leader", lambda: True)
    monkeypatch.setattr("app.worker_runtime.release_leadership", lambda: None)
    calls = []
    monkeypatch.setattr("app.worker_runtime.start_worker_jobs", lambda app: calls.append(app.config["PROCESS_ROLE"]))
    app = create_app("worker_test", instance_path=str(tmp_path), process_role="worker")
    try:
        assert calls == ["worker"]
        assert app.extensions["sync_worker"].owned
    finally:
        assert app.extensions["sync_worker"].shutdown()


def test_second_worker_rejected_before_status_overwrite(worker_app, monkeypatch):
    monkeypatch.setattr("app.worker_runtime.is_leader", lambda: False)
    sentinel = Path(worker_app.instance_path) / STATUS_NAME
    sentinel.write_text("existing worker status")
    runtime = WorkerRuntime(worker_app)
    with pytest.raises(WorkerAlreadyRunning):
        runtime.acquire()
    assert sentinel.read_text() == "existing worker status"
    assert not worker_app.extensions.get("scheduler_threads")


def test_registry_preserves_every_base_job_and_configured_alert_interval(worker_app, monkeypatch):
    from app.config import TestingConfig

    values = {key: getattr(TestingConfig, key) for key in dir(TestingConfig) if key.isupper()}
    for key in list(values):
        if key.startswith("TELEGRAM_") or key == "TEAMS_ALERTS_ENABLED":
            values[key] = ""
    assert configured_jobs(values) == list(_BACKGROUND_JOBS)
    values.update(TELEGRAM_BOT_TOKEN="test-only", TELEGRAM_CHAT_IDS="test-only", TEAMS_ALERTS_ENABLED=True)
    worker_app.config.update(values)
    calls = []
    monkeypatch.setattr("app.background.import_module", lambda name: SimpleNamespace(start=lambda app, interval: calls.append((name, interval))))
    monkeypatch.setattr("app.background._validate_scheduler_offsets", lambda: None)
    start_worker_jobs(worker_app)
    assert calls == [(module, values[key]) for module, key in configured_jobs(values)]
    assert values["INCIDENT_SYNC_INTERVAL_SECONDS"] == TestingConfig.INCIDENT_SYNC_INTERVAL_SECONDS
    assert values["SITE_DOWN_24H_ALERT_RESTORE_INTERVAL_SECONDS"] == TestingConfig.SITE_DOWN_24H_ALERT_RESTORE_INTERVAL_SECONDS


def test_web_role_cannot_start_even_an_accidental_loop(worker_app):
    worker_app.config["PROCESS_ROLE"] = "web"
    with pytest.raises(RuntimeError):
        start_singleton_loop(worker_app, lambda: pytest.fail("job ran"), 300, "blocked-web", "test")


def test_graceful_stop_interrupts_initial_wait_without_sending(worker_app):
    called = []
    start_singleton_loop(worker_app, lambda: called.append(True), 300, "worker-test-wait", "test", first_run_delay=300)
    worker_app.extensions["scheduler_stop_event"].set()
    assert join_scheduler_threads(worker_app, 1)
    assert called == []


def test_running_job_holds_lock_until_finished(worker_app, monkeypatch):
    monkeypatch.setattr("app.worker_runtime.is_leader", lambda: True)
    released = []
    monkeypatch.setattr("app.worker_runtime.release_leadership", lambda: released.append(True))
    runtime = WorkerRuntime(worker_app)
    runtime.acquire()
    entered, finish = threading.Event(), threading.Event()
    start_singleton_loop(worker_app, lambda: (entered.set(), finish.wait(2)), 300, "worker-test-inflight", "test")
    assert entered.wait(1)
    try:
        assert runtime.shutdown(timeout=0.01) is False
        assert runtime.owned and not released
    finally:
        finish.set()
    assert runtime.shutdown(timeout=2)
    assert released == [True]


def test_job_failure_is_recorded_and_next_cycle_recovers(worker_app):
    runtime = WorkerRuntime(worker_app)
    calls = []
    recovered = threading.Event()

    def work():
        calls.append(True)
        if len(calls) == 1:
            raise ValueError("test failure")
        recovered.set()

    start_singleton_loop(worker_app, work, 0.02, "worker-test-recovery", "test")
    assert recovered.wait(2)
    worker_app.extensions["scheduler_stop_event"].set()
    assert join_scheduler_threads(worker_app, 1)
    assert len(calls) >= 2
    assert runtime.jobs["worker-test-recovery"]["last_error"] is None
    assert runtime.jobs["worker-test-recovery"]["last_success_at"]


def test_status_handles_missing_corrupt_and_stale_heartbeat(worker_app):
    directory = Path(worker_app.instance_path)
    assert not read_worker_status(directory)["healthy"]
    status_path = directory / STATUS_NAME
    status_path.write_text("broken")
    assert read_worker_status(directory)["state"] == "unavailable"
    value = {"state": "running", "heartbeat_at": datetime.now(timezone.utc).isoformat(),
             "jobs": {"sync": {"thread_alive": True}}}
    status_path.write_text(json.dumps(value))
    assert read_worker_status(directory)["healthy"]
    value["heartbeat_at"] = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    status_path.write_text(json.dumps(value))
    assert not read_worker_status(directory)["healthy"]


def test_worker_health_api_has_no_store_and_no_jobs_started(client):
    response = client.get("/api/v1/system/sync")
    assert response.status_code == 200
    assert response.json["healthy"] is False
    assert response.headers["Cache-Control"] == "no-store"


def test_cross_process_lock_rejects_duplicate_and_recovers_after_exit():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    script = "import sys;from app.services import leader_lock as lock;lock._LOCK_PORT=int(sys.argv[1]);owned=lock.is_leader();print(int(owned),flush=True);sys.stdin.readline() if owned and len(sys.argv)>2 else None"
    first = subprocess.Popen([sys.executable, "-c", script, str(port), "wait"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert first.stdout.readline().strip() == "1"
        second = subprocess.run([sys.executable, "-c", script, str(port)], capture_output=True, text=True, timeout=15, check=True)
        assert second.stdout.strip() == "0"
    finally:
        first.communicate("stop\n", timeout=15)
    replacement = subprocess.run([sys.executable, "-c", script, str(port)], capture_output=True, text=True, timeout=15, check=True)
    assert replacement.stdout.strip() == "1"


def test_web_restart_preserves_cached_rows_and_persistent_user_data(tmp_path):
    import sqlite3

    create_app("testing", instance_path=str(tmp_path))
    database = tmp_path / "localstorage.db"
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO mentor_sites(site_code, added_at, source) VALUES (?, ?, ?)", ("TEST-SITE", "2026-11-12", "manual"))
        connection.execute("INSERT INTO congestion_blacklist(source, match_kind, match_value, created_at, interface, remark) VALUES (?, ?, ?, ?, ?, ?)",
                           ("eze", "interface", "test-port", "2026-11-12", "port-1", "Saved remark"))
        connection.execute("INSERT INTO site_down_24h_alert_cache(incident_id, incident_ref, down_alert_sent_at) VALUES (?, ?, ?)",
                           ("test-only", "test-reference", "2026-11-12"))
        connection.execute("INSERT INTO incident_reports(id, document_title) VALUES (?, ?)", ("test-report", "Saved report"))
        connection.execute("INSERT INTO sync_meta(table_name, last_synced_at) VALUES (?, ?)", ("site_cache", "2026-11-12"))
        before = {table: connection.execute("SELECT * FROM " + table).fetchall() for table in
                  ("mentor_sites", "congestion_blacklist", "site_down_24h_alert_cache", "incident_reports", "sync_meta")}
    create_app("testing", instance_path=str(tmp_path))
    with sqlite3.connect(database) as connection:
        after = {table: connection.execute("SELECT * FROM " + table).fetchall() for table in before}
    assert before == after


def test_worker_dry_check_does_not_create_app_or_start_jobs(monkeypatch, capsys):
    import worker

    for key in ("LOG_PATH", "LOG_ERROR_PATH", "ATTEMPTS_LOG_PATH", "DASHBOARD_LOG_PATH", "TELEGRAM_LOG_PATH", "WEBHOOK_LOG_PATH", "REQUEST_LOG_PATH"):
        monkeypatch.setenv(key, "logs/test-only.log")
    monkeypatch.setattr("app.create_app", lambda *args, **kwargs: pytest.fail("dry check created app"))
    assert worker.main(["--check"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["timezone"] == "Asia/Phnom_Penh"
    assert any(row["module"].endswith("incident_scheduler") for row in output["jobs"])


def test_packaging_includes_worker_and_launcher():
    import importlib.util

    spec = importlib.util.spec_from_file_location("worker_packager", Path("scripts/build_deploy_zip.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "worker.py" in module.INCLUDE_PATHS
    assert Path("scripts/start_sync_worker.bat").is_file()
    assert Path("scripts/ensure_sync_worker.py").is_file()


def test_cache_reader_can_continue_while_worker_commits(tmp_path):
    import sqlite3

    create_app("testing", instance_path=str(tmp_path))
    database = tmp_path / "localstorage.db"
    with sqlite3.connect(database, timeout=1) as writer, sqlite3.connect(database, timeout=1) as reader:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO mentor_sites(site_code) VALUES ('BEFORE')")
        writer.commit()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO mentor_sites(site_code) VALUES ('AFTER')")
        assert reader.execute("SELECT count(*) FROM mentor_sites").fetchone()[0] == 1
        writer.commit()
        assert reader.execute("SELECT count(*) FROM mentor_sites").fetchone()[0] == 2


def test_real_worker_process_updates_shared_cache_and_survives_web_restart(tmp_path):
    import os
    import sqlite3
    import time

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    instance = tmp_path / "instance"
    stop_file = tmp_path / "stop"
    harness = tmp_path / "worker_harness.py"
    harness.write_text("""
import os
import sys
import threading
import time
from pathlib import Path
from app.config import TestingConfig, config_map
from app.services import leader_lock
from app.services.scheduler_utils import start_singleton_loop
from app.database.cache import get_cache_conn
import app.worker_runtime as runtime
import worker
class IsolatedConfig(TestingConfig):
    TESTING = False
    DEBUG = True
config_map['isolated_worker'] = IsolatedConfig
os.environ['APP_ENV'] = 'isolated_worker'
leader_lock._LOCK_PORT = int(sys.argv[2])
def start_jobs(app):
    def sync():
        with get_cache_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO mentor_sites(site_code, added_at) VALUES ('WORKER-TEST', datetime('now'))")
        return 1
    start_singleton_loop(app, sync, 0.05, 'isolated-sync', 'isolated test')
    def stop_when_requested():
        while not Path(sys.argv[3]).exists():
            time.sleep(0.05)
        app.extensions['sync_worker'].request_stop()
    threading.Thread(target=stop_when_requested, daemon=True).start()
runtime.start_worker_jobs = start_jobs
raise SystemExit(worker.main(['--instance-path', sys.argv[1]]))
""", encoding="utf-8")
    environment = dict(os.environ, PYTHONPATH=str(Path.cwd()))
    command = [sys.executable, str(harness), str(instance), str(port), str(stop_file)]
    process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait_until_running():
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if read_worker_status(instance)["healthy"]:
                return
            assert process.poll() is None, "isolated worker exited unexpectedly"
            time.sleep(0.05)
        pytest.fail("worker heartbeat did not become ready")

    try:
        wait_until_running()
        status = read_worker_status(instance)
        worker_pid = status["pid"]
        assert isinstance(worker_pid, int) and worker_pid > 0
        duplicate = subprocess.run(command, env=environment, capture_output=True, timeout=15)
        assert duplicate.returncode == 2
        assert read_worker_status(instance)["pid"] == worker_pid
        for _ in range(2):
            web = create_app("testing", instance_path=str(instance))
            assert not web.extensions.get("scheduler_threads")
            assert web.test_client().get("/api/v1/system/sync").json["healthy"]
        with sqlite3.connect(instance / "localstorage.db") as connection:
            assert connection.execute("SELECT site_code FROM mentor_sites").fetchone()[0] == "WORKER-TEST"
    finally:
        stop_result = subprocess.run(
            [sys.executable, "worker.py", "--stop", "--instance-path", str(instance)],
            env=environment, capture_output=True, timeout=35,
        )
        stop_file.touch()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    assert stop_result.returncode == 0
    assert process.returncode == 0
    assert read_worker_status(instance)["state"] == "stopped"
    stop_file.unlink()
    replacement = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    process = replacement
    try:
        wait_until_running()
        assert read_worker_status(instance)["pid"] != worker_pid
    finally:
        stop_file.touch()
        try:
            replacement.wait(timeout=15)
        except subprocess.TimeoutExpired:
            replacement.kill()
            replacement.wait(timeout=5)
    assert replacement.returncode == 0


def test_old_stop_request_does_not_stop_new_worker_session(worker_app):
    from app.worker_runtime import STOP_NAME

    runtime = WorkerRuntime(worker_app)
    path = Path(worker_app.instance_path) / STOP_NAME
    path.write_text(json.dumps({"pid": 0, "started_at": runtime.started_at}))
    runtime.check_stop_request()
    assert not runtime.stop_event.is_set()
    import os

    path.write_text(json.dumps({"pid": os.getpid(), "started_at": runtime.started_at}))
    runtime.check_stop_request()
    assert runtime.stop_event.is_set()


def test_normal_stop_is_not_reported_as_dead_scheduler(monkeypatch):
    import worker

    for key in ("LOG_PATH", "LOG_ERROR_PATH", "ATTEMPTS_LOG_PATH", "DASHBOARD_LOG_PATH", "TELEGRAM_LOG_PATH", "WEBHOOK_LOG_PATH", "REQUEST_LOG_PATH"):
        monkeypatch.setenv(key, "logs/test-only.log")
    stop = threading.Event()
    shutdown = []
    runtime = SimpleNamespace(
        stop_event=stop,
        check_stop_request=stop.set,
        request_stop=stop.set,
        shutdown=lambda: shutdown.append(True) or True,
    )
    fake_app = SimpleNamespace(extensions={
        "sync_worker": runtime,
        "scheduler_threads": [SimpleNamespace(is_alive=lambda: False)],
    })
    monkeypatch.setattr("app.create_app", lambda **kwargs: fake_app)
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)
    assert worker.main([]) == 0
    assert shutdown == [True]
