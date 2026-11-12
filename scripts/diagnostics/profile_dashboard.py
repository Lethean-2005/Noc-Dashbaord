"""Measure initial/full/chart render time against an isolated cache snapshot."""
import argparse
from contextlib import closing
import json
import logging
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.runs <= 20:
        parser.error("--runs must be between 1 and 20")
    logging.disable(logging.CRITICAL)
    from app import create_app

    source = ROOT / "instance/localstorage.db"
    if not source.is_file():
        parser.error("The local cache does not exist yet")
    routes = {"full_render": "/?load_performance=1", "initial_render": "/", "historical_section": "/performance-cards"}
    results = {label: [] for label in routes}
    sizes = {}
    with tempfile.TemporaryDirectory(prefix="noc-perf-") as folder:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            with closing(sqlite3.connect(Path(folder) / "localstorage.db")) as clone:
                origin.backup(clone)
        app = create_app("testing", instance_path=folder)
        client = app.test_client()
        for route in routes.values():
            response = client.get(route)
            if response.status_code != 200:
                raise RuntimeError(f"Profiling request failed: {route}")
        for _ in range(args.runs):
            for label, route in routes.items():
                started = time.perf_counter()
                response = client.get(route)
                results[label].append((time.perf_counter() - started) * 1000)
                sizes[label] = len(response.data)
    report = {label: {"median_ms": round(statistics.median(values), 1),
                      "html_KiB": round(sizes[label] / 1024, 1), "runs": len(values)}
              for label, values in results.items()}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
