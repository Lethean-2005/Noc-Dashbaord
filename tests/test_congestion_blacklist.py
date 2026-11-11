"""Exclusions persist per owner, device and interface."""
from urllib.parse import urlencode

from app.database.cache import get_cache_conn, init_cache_db
from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.alarm.congestion_blacklist_repository import CongestionBlacklistRepository
from app.services.alarm.alarm_service import AlarmService
from app.services.alarm.congestion_blacklist_service import CongestionBlacklistService, match_key


def alarm(row_id="c1", source="tct", alarm="congestion", code="I0215", **extra):
    row = dict(id=row_id, alarm=alarm, alarm_name=source.upper() + "_" + alarm.upper(),
               device_name="DX-PNHCC-RB01-DS01", ip_address="10.22.2.9", pop_name="CCOC-EZECOM-PVT",
               pop_code=code, pro_owner="Telcotech" if source == "tct" else "Ezecom",
               down_time="2026-11-05 15:03:08", interface="GigabitEthernet2/1/2")
    row.update(extra)
    complete = {name: "" for name in AlarmCacheRepository.columns}
    complete.update(row)
    return complete


def seed(app, table, rows):
    with app.app_context():
        AlarmCacheRepository().replace_all(table, rows)


def test_exclude_filters_only_selected_interface_across_restart(app):
    original = alarm()
    seed(app, "tct_alarm_cache", [original, alarm("cpu", alarm="cpu")])
    with app.app_context():
        service = AlarmService()
        assert service.get_tct_counts()["congestion"] == 1
        CongestionBlacklistService().exclude(original, "tct", "tester")
        assert service.get_tct_counts()["congestion"] == 0
        assert service.get_tct_counts()["cpu"] == 1
        assert [r["id"] for r in service.get_tct_details()] == ["cpu"]
        # Only the selected interface stays hidden after cache replacement.
        AlarmCacheRepository().replace_all("tct_alarm_cache", [alarm("new", device_name="RENAMED"), alarm("other-port", interface="GigabitEthernet1/1")])
        init_cache_db()  # Simulates schema initialization after restart.
        assert CongestionBlacklistRepository().fetch_all()
        assert [r["id"] for r in AlarmService().get_tct_details()] == ["other-port"]
        rule = CongestionBlacklistRepository().fetch_all()[0]
        CongestionBlacklistRepository().remove(rule["id"])
        assert len(service.get_tct_details()) == 2
        assert service.get_tct_counts()["congestion"] == 1


def test_exclusions_are_provider_specific_and_include_both_congestion_names(app):
    with app.app_context():
        CongestionBlacklistService().exclude(alarm(), "tct", "tester")
        service = CongestionBlacklistService()
        assert service.filter_rows([alarm(alarm="bandwidth")], "tct") == []
        eze = alarm(source="eze", alarm="BANDWIDTH")
        assert service.filter_rows([eze], "eze") == [eze]
        service.exclude(eze, "eze", "tester")
        assert service.filter_rows([eze], "eze") == []
        assert service.filter_rows([alarm(source="eze", alarm="PORT")], "eze")
        assert len(CongestionBlacklistRepository().fetch_all()) == 2


def test_no_site_code_uses_device_ip_not_all_empty_sites(app):
    with app.app_context():
        service = CongestionBlacklistService()
        service.exclude(alarm(code=""), "tct", "tester")
        assert service.filter_rows([alarm("new", code="")], "tct") == []
        assert service.filter_rows([alarm("other", code="", ip_address="10.22.2.10")], "tct")
        assert match_key(alarm(code=""), "tct")[1] == "interface"


def test_blacklist_is_idempotent_and_rejects_non_congestion(app, client):
    seed(app, "tct_alarm_cache", [alarm(), alarm("cpu", alarm="cpu")])
    form = {"source": "tct", "id": "c1", "return_to": "/congestion"}
    assert client.post('/alarms/congestion/exclude', data=form).status_code == 302
    assert client.post('/alarms/congestion/exclude', data=form).status_code == 302
    assert client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"cpu"}).status_code == 400
    assert client.post('/alarms/congestion/exclude', data={"source":"isp_pop", "id":"c1"}).status_code == 400
    with app.app_context():
        assert len(CongestionBlacklistRepository().fetch_all()) == 1


def test_excluded_history_is_removed_from_rankings_summaries_and_csv(app, client):
    seed(app, "tct_alarm_cache", [alarm()])
    seed(app, "congestion_history_cache", [alarm("history1"), alarm("history2", code="OTHER", device_name="VISIBLE_DEVICE", ip_address="10.22.2.10")])
    with app.app_context():
        CongestionBlacklistService().exclude(alarm(), "tct", "tester")
        service = AlarmService()
        top = service.get_congestion_top_devices()
        assert [r["device_name"] for r in top["bars"]] == ["VISIBLE_DEVICE"]
        assert top["total"] == 1
        assert service.get_congestion_device_interface_summary("DX-PNHCC-RB01-DS01") == []
        weekly = service.get_congestion_week_interface_summary("2026-11-02")
        assert [r["device_name"] for r in weekly] == ["VISIBLE_DEVICE"]
    export = client.get('/drilldown/download?' + urlencode({"scope":"Congestion History", "congestion_week":"2026-11-02"}))
    assert export.status_code == 200
    assert "VISIBLE_DEVICE" in export.get_data(as_text=True)
    assert "DX-PNHCC-RB01-DS01" not in export.get_data(as_text=True)


def test_blacklist_popup_restore_and_safe_return_url(app, client):
    seed(app, "eze_alarm_cache", [alarm(source="eze", alarm="BANDWIDTH")])
    response = client.post('/alarms/congestion/exclude', data={"source":"eze", "id":"c1", "return_to":"https://example.invalid/"})
    assert response.headers['Location'] == '/congestion'
    popup = client.get('/alarms/congestion/blacklist')
    assert popup.status_code == 200
    assert "CCOC-EZECOM-PVT" in popup.get_data(as_text=True)
    with app.app_context():
        rule = CongestionBlacklistRepository().fetch_all()[0]
    response = client.post(f'/alarms/congestion/blacklist/{rule["id"]}/restore', data={"return_to":"/congestion"})
    assert response.status_code == 302
    with app.app_context():
        assert CongestionBlacklistRepository().fetch_all() == []
        assert len(AlarmService().get_eze_details()) == 1


def test_congestion_actions_render_only_on_eligible_rows_and_history(app, client):
    seed(app, "tct_alarm_cache", [alarm(), alarm("cpu", alarm="cpu")])
    page = client.get('/drilldown?' + urlencode({"scope":"IP Telcotech/Cellcard"}))
    assert page.status_code == 200
    assert page.get_data(as_text=True).count('data-congestion-exclude\n') == 1
    seed(app, "congestion_history_cache", [alarm("history1")])
    page = client.get('/drilldown?' + urlencode({"scope":"Congestion History", "type":"DX-PNHCC-RB01-DS01"}))
    assert page.status_code == 200
    assert 'data-source="congestion_history"' in page.get_data(as_text=True)
    assert '<th>Action</th>' in page.get_data(as_text=True)


def test_blacklist_writes_keep_csrf_protection(app, client):
    app.config['WTF_CSRF_ENABLED'] = True
    response = client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"c1"})
    assert response.status_code == 400


def test_history_action_resolves_original_alarm_and_survives_refill(app, client):
    seed(app, "congestion_history_cache", [alarm("history1")])
    with app.app_context():
        summary = AlarmService().get_congestion_device_interface_summary("DX-PNHCC-RB01-DS01")
        assert summary[0]["id"] == "history1"
    response = client.post('/alarms/congestion/exclude', data={"source":"congestion_history", "id":"history1", "return_to":"/congestion"})
    assert response.status_code == 302
    seed(app, "congestion_history_cache", [alarm("history-new")])
    with app.app_context():
        assert AlarmService().get_congestion_top_devices()["bars"] == []


def test_missing_or_unidentifiable_alarm_cannot_create_exclusion(app, client):
    assert client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"missing"}).status_code == 404
    seed(app, "tct_alarm_cache", [alarm(code="", device_name="", ip_address="")])
    assert client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"c1"}).status_code == 400
    with app.app_context():
        assert CongestionBlacklistRepository().fetch_all() == []


def test_empty_blacklist_keeps_table_and_illustrated_empty_state(client):
    response = client.get('/alarms/congestion/blacklist')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<th>Owner</th>' in html
    assert 'No data excluded congestion' in html
    assert 'no-data-available.svg' in html


def test_blacklist_keeps_interface_and_info_after_restart(app, client):
    with app.app_context():
        CongestionBlacklistService().exclude(alarm(additional_info="BandwidthUsage=90 <test>", note="Monitor <link>"), "tct", "tester")
        init_cache_db()
        rule = CongestionBlacklistRepository().fetch_all()[0]
        assert rule["interface"] == "GigabitEthernet2/1/2"
        assert rule["note"] == "Monitor <link>"
        assert rule["ip_address"] == "10.22.2.9"
        assert rule["additional_info"] == "BandwidthUsage=90 <test>"
    html = client.get('/alarms/congestion/blacklist').get_data(as_text=True)
    assert '<th>Interface</th>' in html
    assert '<th>IP Address</th>' in html
    assert '<th>Note</th>' in html
    assert '10.22.2.9' in html
    assert 'Monitor &lt;link&gt;' in html
    assert '<th>Additional Info</th>' in html
    assert 'GigabitEthernet2/1/2' in html
    assert 'BandwidthUsage=90 &lt;test&gt;' in html


def test_old_blacklist_schema_upgrades_without_losing_rules(app):
    with app.app_context():
        service = CongestionBlacklistService()
        service.exclude(alarm(), "tct", "tester")
        conn = get_cache_conn()
        try:
            for column in ("interface", "additional_info", "note", "remark"):
                conn.execute(f"ALTER TABLE congestion_blacklist DROP COLUMN {column}")
            conn.commit()
        finally:
            conn.close()
        init_cache_db()
        rules = CongestionBlacklistRepository().fetch_all()
        assert len(rules) == 1
        assert rules[0]["pop_code"] == "I0215"
        assert rules[0]["interface"] is None
        assert rules[0]["note"] is None
        assert rules[0]["remark"] is None
        assert service.filter_rows([alarm()], "tct") == [alarm()]


def test_interface_rules_keep_other_ports_devices_and_alarm_types_visible(app):
    with app.app_context():
        service = CongestionBlacklistService()
        selected = alarm(interface="XGigabitEthernet0/0/22")
        other_port = alarm("port23", interface="XGigabitEthernet0/0/23")
        other_device = alarm("device2", interface="XGigabitEthernet0/0/22", ip_address="10.22.2.10")
        other_type = alarm("cpu", alarm="cpu", interface="XGigabitEthernet0/0/22")
        service.exclude(selected, "tct", "tester", "Temporary maintenance")
        assert service.filter_rows([selected, other_port, other_device, other_type], "tct") == [other_port, other_device, other_type]
        service.exclude(other_port, "tct", "tester", "Separate port")
        assert len(CongestionBlacklistRepository().fetch_all()) == 2
        init_cache_db()
        assert service.filter_rows([selected, other_port, other_device], "tct") == [other_device]


def test_old_site_rule_with_interface_is_narrowed_without_losing_remark(app):
    with app.app_context():
        service = CongestionBlacklistService()
        service.exclude(alarm(), "tct", "tester", "Keep this reason")
        conn = get_cache_conn()
        try:
            conn.execute("UPDATE congestion_blacklist SET match_kind = 'site', match_value = 'i0215'")
            conn.commit()
        finally:
            conn.close()
        other_port = alarm("other", interface="GigabitEthernet1/1")
        assert service.filter_rows([alarm(), other_port], "tct") == [other_port]
        assert CongestionBlacklistRepository().fetch_all()[0]["remark"] == "Keep this reason"


def test_exclude_requires_interface_and_persists_escaped_remark(app, client):
    seed(app, "tct_alarm_cache", [alarm(), alarm("missing-port", interface="")])
    assert client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"missing-port"}).status_code == 400
    assert client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"c1", "remark":"x" * 1001}).status_code == 400
    response = client.post('/alarms/congestion/exclude', data={"source":"tct", "id":"c1", "remark":" Maintenance <port> "})
    assert response.status_code == 302
    with app.app_context():
        init_cache_db()
        assert CongestionBlacklistRepository().fetch_all()[0]["remark"] == "Maintenance <port>"
    html = client.get('/alarms/congestion/blacklist').get_data(as_text=True)
    assert '<th>Remark</th>' in html
    assert 'Maintenance &lt;port&gt;' in html
    assert 'Only this interface on this device' not in html


def test_rankings_week_summary_and_export_keep_other_interface(app, client):
    selected = alarm("port22", interface="XGigabitEthernet0/0/22")
    remaining = alarm("port23", interface="XGigabitEthernet0/0/23")
    seed(app, "congestion_history_cache", [selected, remaining])
    with app.app_context():
        CongestionBlacklistService().exclude(selected, "tct", "tester", "Port maintenance")
        service = AlarmService()
        top = service.get_congestion_top_devices()
        assert top["total"] == 1
        assert len(top["bars"]) == 1
        assert top["bars"][0]["device_name"] == selected["device_name"]
        summary = service.get_congestion_device_interface_summary(selected["device_name"])
        assert [row["interface"] for row in summary] == [remaining["interface"]]
        weekly = service.get_congestion_week_interface_summary("2026-11-02")
        assert [row["interface"] for row in weekly] == [remaining["interface"]]
    export = client.get('/drilldown/download?' + urlencode({"scope":"Congestion History", "congestion_week":"2026-11-02"}))
    assert export.status_code == 200
    assert selected["interface"] not in export.get_data(as_text=True)
    assert remaining["interface"] in export.get_data(as_text=True)
