"""Delivery policy shared by workers and manual notification entry points."""
import os

from flask import current_app, has_app_context


def notifications_enabled(config=None):
    """Keep syncing when delivery is disabled; preserve existing installs by default."""
    if config is None:
        config = current_app.config if has_app_context() else os.environ
    value = config.get("NOTIFICATIONS_ENABLED", True)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
