"""Shared pytest fixtures.

The app queries hand-written SQL against tables that, in a real deployment, already
exist in Postgres. For tests we stand up the same tables in the in-memory SQLite
database so routes can be exercised end-to-end without a live Postgres instance.
"""
import pytest
from sqlalchemy import text

from app import create_app
from app.extensions import db

SCHEMA = """
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE reports (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE mentor_sessions (
    id INTEGER PRIMARY KEY,
    mentee TEXT NOT NULL,
    mentor TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL
);
"""


@pytest.fixture
def app():
    flask_app = create_app("testing")
    with flask_app.app_context():
        db.create_all()
        for statement in SCHEMA.strip().split(";"):
            if statement.strip():
                db.session.execute(text(statement))
        db.session.commit()
        yield flask_app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
