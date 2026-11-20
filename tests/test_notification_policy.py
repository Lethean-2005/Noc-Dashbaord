"""Local sync-only mode must never send or consume notification ledger entries."""
from importlib import import_module

import pytest
from flask import Flask

from app.background import configured_jobs
from app.services.notification_policy import notifications_enabled


@pytest.mark.parametrize("value,expected", [(False, False), (True, True), ("false", False), ("true", True), ("0", False), ("on", True)])
def test_setting(value, expected):
    assert notifications_enabled({"NOTIFICATIONS_ENABLED": value}) is expected


def test_existing_installations_remain_enabled():
    assert notifications_enabled({})


def test_sync_jobs_remain_available_without_delivery():
    config = {"NOTIFICATIONS_ENABLED": False, "TEAMS_ALERTS_ENABLED": True,
              "TELEGRAM_BOT_TOKEN": "test-only", "TELEGRAM_CHAT_IDS": "test-only"}
    disabled = configured_jobs(config)
    enabled = configured_jobs({**config, "NOTIFICATIONS_ENABLED": True})
    assert disabled
    assert all("telegram" not in module and module != "webhook" and "24h_alert" not in module
               for module, _ in disabled)
    assert set(disabled) == {(module, key) for module, key in enabled
                             if "telegram" not in module and module != "webhook" and "24h_alert" not in module}


@pytest.mark.parametrize("module,function,expected", [
    ("app.services.incident.site_down_24h_alert_service", "check_and_send_down_alerts", 0),
    ("app.services.incident.site_down_24h_alert_service", "check_and_send_restore_alerts", 0),
    ("app.services.telegram.telegram_alert", "send_site_down_alert", None),
    ("app.services.telegram.telegram_inc_wo_alert", "send_inc_wo_site_down_alert", None),
    ("app.services.telegram.telegram_inc_wo_power_alert", "send_inc_wo_category_power_alert", None),
    ("app.services.telegram.telegram_inc_wo_general_alert", "send_inc_wo_general_alert", None),
])
def test_disabled_public_sends_do_not_read_sources_or_write_ledger(module, function, expected, monkeypatch):
    app = Flask(__name__)
    app.config["NOTIFICATIONS_ENABLED"] = False
    service = import_module(module)
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled notification reached database or network")
    import requests
    monkeypatch.setattr(requests, "post", forbidden)
    if hasattr(service, "SiteDown24hAlertCacheRepository"):
        monkeypatch.setattr(service, "SiteDown24hAlertCacheRepository", forbidden)
    with app.app_context():
        result = getattr(service, function)()
    if expected == 0:
        assert result == 0
    else:
        assert result["sent"] is False


def test_disabled_teams_and_transport_do_not_send(monkeypatch):
    from webhook import common
    app = Flask(__name__)
    app.config["NOTIFICATIONS_ENABLED"] = False
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled delivery reached transport")
    monkeypatch.setattr(common, "_pool", forbidden)
    with app.app_context():
        assert common.send(None)["sent"] is False
        with pytest.raises(RuntimeError, match="notifications disabled"):
            common._post_json("https://example.invalid", {})
