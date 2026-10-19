"""Shared Flask extension instances.

Instantiated here (unbound) and initialized against the app in the
application factory, so they can be imported anywhere without circular imports.
"""

from flask_compress import Compress
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "dashboard.index"
csrf = CSRFProtect()
# gzip/Brotli-compresses text responses (HTML/CSS/JS/JSON) — confirmed
# via a direct header check that none of this app's responses were
# compressed at all before this; CSS/JS typically shrink 70-80% with
# compression, which matters every ~5 minutes since the dashboard's own
# auto-reload (dashboard/index.html) does a full location.reload().
compress = Compress()


@login_manager.user_loader
def load_user(user_id):
    # Stub until a User model/auth system is added; Flask-Login requires this
    # callback to be registered even when no one can be logged in yet.
    return None
