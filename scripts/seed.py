"""Seed the local database schema for development."""
from app import create_app
from app.extensions import db


def run():
    app = create_app("development")
    with app.app_context():
        db.create_all()
        print("Database tables created.")


if __name__ == "__main__":
    run()
