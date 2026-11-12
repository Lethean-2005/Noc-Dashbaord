"""CLI startup must not silently leave cache synchronization stopped."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def entry(monkeypatch):
    calls = []
    fake = SimpleNamespace(config={"DEBUG": True, "HOST": "127.0.0.1", "PORT": 5000},
                           run=lambda **kwargs: calls.append("web"))
    monkeypatch.setattr("app.create_app", lambda *args, **kwargs: fake)
    spec = importlib.util.spec_from_file_location("isolated_run", Path("run.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_cli_starts_independent_worker_before_web(entry, monkeypatch):
    module, calls = entry
    monkeypatch.setattr("scripts.ensure_sync_worker.main", lambda: calls.append("worker") or 0)
    assert module.main([]) == 0
    assert calls == ["worker", "web"]


def test_web_only_mode_never_starts_worker(entry, monkeypatch):
    module, calls = entry
    monkeypatch.setattr("scripts.ensure_sync_worker.main", lambda: pytest.fail("worker started"))
    assert module.main(["--web-only"]) == 0
    assert calls == ["web"]


def test_worker_startup_failure_is_not_silently_ignored(entry, monkeypatch):
    module, calls = entry
    monkeypatch.setattr("scripts.ensure_sync_worker.main", lambda: 1)
    assert module.main([]) == 1
    assert calls == []
