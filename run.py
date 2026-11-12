"""Web server entry point; scheduled work runs in the independent worker.py.

Entry point: `python run.py`, or via the Flask CLI with `flask --app run run`.

APP_ENV (set in .env) selects the config class from app/config.py, which
determines the database connection, debug mode, and host/port.
"""

import argparse
import os

from app import create_app

app = create_app(os.environ.get("APP_ENV", "development"), process_role="web")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the NOC web server and ensure its separate worker is running.")
    parser.add_argument("--web-only", action="store_true", help="Serve HTTP only; use when another service manages the worker")
    args = parser.parse_args(argv)
    if not args.web_only:
        from scripts.ensure_sync_worker import main as ensure_worker

        result = ensure_worker()
        if result:
            return result
    if app.config["DEBUG"]:
        # threaded=True: Werkzeug's dev server otherwise handles exactly one
        # request at a time — with several NOC staff hitting the dashboard
        # around the same moment, requests would queue up behind each other
        # instead of running concurrently. Kept for local development only,
        # since it still gives the Werkzeug auto-reloader/debugger that
        # waitress doesn't have.
        app.run(host=app.config["HOST"], port=app.config["PORT"], debug=True, threaded=True)
    else:
        # waitress: a real WSGI server (runs on Windows, unlike gunicorn) —
        # handles multiple requests concurrently properly, unlike the
        # Werkzeug dev server outside of its debug/threaded mode above.
        # Use this for anything beyond local dev. threads defaults to 8
        # (waitress's own default is 4 — see app/config.py's
        # WAITRESS_THREADS for why that's too few here).
        from waitress import serve

        serve(
            app,
            host=app.config["HOST"],
            port=app.config["PORT"],
            threads=app.config["WAITRESS_THREADS"],
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
