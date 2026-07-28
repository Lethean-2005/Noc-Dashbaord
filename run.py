"""Entry point: `python run.py`, or via the Flask CLI with `flask --app run run`.

APP_ENV (set in .env) selects the config class from app/config.py, which
determines the database connection, debug mode, and host/port.
"""
import os

from app import create_app

app = create_app(os.environ.get("APP_ENV", "development"))

if __name__ == "__main__":
    # threaded=True: Werkzeug's dev server otherwise handles exactly one
    # request at a time — with several NOC staff hitting the dashboard
    # around the same moment, requests would queue up behind each other
    # instead of running concurrently. This is still the Werkzeug dev
    # server (see its own "development server" warning below), not a
    # production WSGI server — for real multi-user production traffic,
    # a dedicated server (e.g. waitress, which runs on Windows unlike
    # gunicorn) is the more robust long-term choice.
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"], threaded=True)
