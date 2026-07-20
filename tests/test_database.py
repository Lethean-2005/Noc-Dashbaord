from app.database.sql_loader import load_queries


def test_dashboard_queries_load():
    queries = load_queries("dashboard")
    assert "summary" in queries
    assert "overview_metrics" in queries


def test_reports_queries_load():
    queries = load_queries("reports")
    assert "list" in queries


def test_mentor_queries_load():
    queries = load_queries("mentor")
    assert "sessions" in queries
