"""Web server entry point; scheduled work runs in the independent worker.py.

Entry point: `python run.py`, or via the Flask CLI with `flask --app run run`.

APP_ENV (set in .env) selects the config class from app/config.py, which
determines the database connection, debug mode, and host/port.
"""

import argparse
import os
from pathlib import Path

from app import create_app

app = create_app(os.environ.get("APP_ENV", "development"), process_role="web")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the NOC web server and ensure its separate worker is running.")
    parser.add_argument("--web-only", action="store_true", help="Serve HTTP only; use when another service manages the worker")
    parser.add_argument("--stop-worker-on-exit", action="store_true", help="Stop this project worker when the web server exits")
    args = parser.parse_args(argv)
    if not args.web_only:
        from scripts.ensure_sync_worker import main as ensure_worker

        result = ensure_worker()
        if result:
            return result
    try:
        if app.config["DEBUG"]:
            app.run(host=app.config["HOST"], port=app.config["PORT"], debug=True, threaded=True)
        else:
            from waitress import serve

            serve(app, host=app.config["HOST"], port=app.config["PORT"],
                  threads=app.config["WAITRESS_THREADS"])
    except KeyboardInterrupt:
        pass
    # Reload exits and bind failures propagate without stopping a shared worker.
    if not args.web_only or args.stop_worker_on_exit:
        from app.services.worker_handoff import stop_current_worker

        if not stop_current_worker(Path(__file__).resolve().parent):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
