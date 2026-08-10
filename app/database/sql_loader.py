"""Shared loader for named `.sql` query files.

Both app/database/connection.py (Postgres) and app/database/mssql.py (MSSQL)
parse their queries the same way — split a domain's .sql file on `-- name:`
marker comments — so that parsing logic lives here once instead of being
copy-pasted in both places.
"""

from functools import lru_cache
from pathlib import Path

QUERIES_DIR = Path(__file__).parent / "queries"


@lru_cache(maxsize=None)
def load_queries(domain):
    """Parse app/database/queries/<domain>.sql into {query_name: sql_text}."""
    path = QUERIES_DIR / f"{domain}.sql"
    queries = {}
    name = None
    lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        marker = line.strip()
        if marker.startswith("-- name:"):
            if name:
                queries[name] = "\n".join(lines).strip()
            name = marker.split("-- name:", 1)[1].strip()
            lines = []
        else:
            lines.append(line)

    if name:
        queries[name] = "\n".join(lines).strip()

    return queries
