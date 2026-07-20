"""Entry point: `python run.py`, or via the Flask CLI with `flask --app run run`.

APP_ENV (set in .env) selects the config class from app/config.py, which
determines the database connection, debug mode, and host/port.
"""
import os

from app import create_app

app = create_app(os.environ.get("APP_ENV", "development"))

if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])
