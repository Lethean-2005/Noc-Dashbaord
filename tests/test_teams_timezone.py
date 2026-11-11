"""Teams timestamps use Cambodia time even on servers with another timezone."""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from webhook.common import AlertSpec, build_connector_card


def test_teams_card_requests_cambodia_timezone():
    spec = AlertSpec(key="test", title="Test", env_var="TEST_WEBHOOK", fetch=lambda: [], columns=[], report_path="/")
    with patch("webhook.common.datetime") as clock:
        clock.now.return_value = datetime(2026, 11, 5, 14, 30, tzinfo=ZoneInfo("Asia/Phnom_Penh"))
        card = build_connector_card(spec, [], 0)
    clock.now.assert_called_once_with(ZoneInfo("Asia/Phnom_Penh"))
    assert "2026-11-05 14:30" in card["sections"][0]["activitySubtitle"]
