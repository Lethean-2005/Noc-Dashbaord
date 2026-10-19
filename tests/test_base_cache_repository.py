"""Tests for BaseCacheRepository.replace_all()'s retry-on-lock behavior —
~11 independent background schedulers all write to the same SQLite file
(see app/__init__.py's _BACKGROUND_JOBS), each on its own timer, and a
burst where several land at once can exceed get_cache_conn()'s own 10s
busy_timeout and fail outright with "database is locked" (confirmed live
in production logs). These tests fake out get_cache_conn() with a
controllable connection instead of real SQLite lock contention, which
would need real concurrent threads/timing to reproduce reliably.
"""

import sqlite3

import pytest

from app.repositories import base_cache_repository as repo_module
from app.repositories.base_cache_repository import BaseCacheRepository


class _FakeConn:
    """execute() raises for the first `fail_times` calls it's asked to
    (via the shared `state` dict), then behaves like a normal in-memory
    connection would — tracks commit()/rollback()/close() calls too."""

    def __init__(self, state):
        self.state = state
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def execute(self, sql, params=None):
        if sql.startswith("DELETE") and self.state["calls"] < self.state["fail_times"]:
            self.state["calls"] += 1
            raise sqlite3.OperationalError(self.state["error_message"])
        return self

    def executemany(self, sql, rows):
        return self

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _FakeRepo(BaseCacheRepository):
    valid_tables = ("some_table",)
    columns = ("id", "name")
    order_by = "id"


@pytest.fixture
def make_repo(monkeypatch):
    """Returns a (repo, state, conns) tuple — `state["fail_times"]` sets
    how many DELETE calls raise before succeeding; `conns` collects every
    _FakeConn created, so a test can assert commit/rollback/close counts
    across every attempt, not just the last one."""
    def _make(fail_times, error_message="database is locked"):
        state = {"calls": 0, "fail_times": fail_times, "error_message": error_message}
        conns = []

        def fake_get_cache_conn():
            conn = _FakeConn(state)
            conns.append(conn)
            return conn

        monkeypatch.setattr(repo_module, "get_cache_conn", fake_get_cache_conn)
        monkeypatch.setattr(repo_module.time, "sleep", lambda seconds: None)
        return _FakeRepo(), conns

    return _make


def test_replace_all_succeeds_immediately_when_never_locked(make_repo, app):
    with app.app_context():
        repo, conns = make_repo(fail_times=0)
        repo.replace_all("some_table", [{"id": 1, "name": "a"}])

        assert len(conns) == 1
        assert conns[0].commits == 1
        assert conns[0].rollbacks == 0
        assert conns[0].closed is True


def test_replace_all_retries_then_succeeds(make_repo, app):
    with app.app_context():
        repo, conns = make_repo(fail_times=2)
        repo.replace_all("some_table", [{"id": 1, "name": "a"}])

        assert len(conns) == 3
        assert [c.rollbacks for c in conns] == [1, 1, 0]
        assert [c.commits for c in conns] == [0, 0, 1]
        assert all(c.closed for c in conns)


def test_replace_all_raises_after_exhausting_all_retries(make_repo, app):
    with app.app_context():
        repo, conns = make_repo(fail_times=10)

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            repo.replace_all("some_table", [{"id": 1, "name": "a"}])

        assert len(conns) == 4
        assert all(c.rollbacks == 1 for c in conns)
        assert all(c.commits == 0 for c in conns)
        assert all(c.closed for c in conns)


def test_replace_all_does_not_retry_a_non_lock_operational_error(make_repo, app):
    with app.app_context():
        repo, conns = make_repo(fail_times=10, error_message="no such table: some_table")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            repo.replace_all("some_table", [{"id": 1, "name": "a"}])

        assert len(conns) == 1
        assert conns[0].rollbacks == 1
        assert conns[0].closed is True
