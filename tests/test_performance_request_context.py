"""Optional duration filters must not require an HTTP request to parse badge links."""
from contextvars import Context

from flask import has_request_context
import pytest

from app.routes.dashboard import _resolve_duration_selection


@pytest.mark.parametrize("badge,expected", [
    ("short_2026-W45", ({0}, "2026-W45")),
    ("short,long_2026-W45", ({0, 1}, "2026-W45")),
    ("unknown_2026-W45", (None, None)),
    (None, (None, None)),
])
def test_duration_selection_without_any_inherited_request(app, badge, expected):
    def check():
        with app.app_context():
            assert not has_request_context()
            assert _resolve_duration_selection(badge, {"short": "short", "long": "long"}, ("short", "long")) == expected
    Context().run(check)


def test_request_duration_filters_still_override_badge(app):
    with app.test_request_context("/?duration_bucket=long&week=2026-W47"):
        assert _resolve_duration_selection("short_2026-W45", {"short": "short", "long": "long"}, ("short", "long")) == ({1}, "2026-W47")
