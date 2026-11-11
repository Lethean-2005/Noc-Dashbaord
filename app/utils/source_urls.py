"""One configurable Streamline base for UI, exports, and alert links."""
from flask import current_app, has_app_context
from app.config import Config


def source_url(path):
    base = current_app.config["STREAMLINE_BASE_URL"] if has_app_context() else Config.STREAMLINE_BASE_URL
    return base.rstrip("/") + "/" + path.lstrip("/")
