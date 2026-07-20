"""Shared Flask extension instances.

Instantiated here (unbound) and initialized against the app in the
application factory, so they can be imported anywhere without circular imports.
"""
from flask_caching import Cache
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
cache = Cache()
login_manager = LoginManager()
login_manager.login_view = "dashboard.index"
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id):
    # Stub until a User model/auth system is added; Flask-Login requires this
    # callback to be registered even when no one can be logged in yet.
    return None
