"""Capture real UI using isolated sample fixtures. All non-GET requests are blocked."""
from pathlib import Path
import sys
import tempfile
import logging
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flask import render_template
from app import create_app
from playwright.sync_api import sync_playwright

OUT = ROOT / "app/static/images/help/demos"
ROW = dict(id="demo-record-1", rtid="INC-DEMO-001", pop_name="Demo POP",
           pop_code="DEMO01", pro_owner="Ezecom", device_name="DEMO-RTR-01",
           ip_address="192.0.2.10", alarm="BANDWIDTH", alarm_name="EZE_BANDWIDTH",
           down_time="11-Nov-2026 09:00", outage_min=60,
           interface="XGigabitEthernet0/0/22", province="Demo province",
           note="", additional_info="Sample bandwidth event")
RULE = dict(id=1,source="eze",pop_name="Demo POP",pop_code="DEMO01",
            device_name="DEMO-RTR-01",ip_address="192.0.2.10",
            interface="XGigabitEthernet0/0/22",additional_info="Sample bandwidth event",
            note="Investigating sample port",remark="Demo: approved interface monitoring exception",
            created_by="Demo Operator",created_at="11-Nov-2026 10:00")


def capture():
    logging.disable(logging.CRITICAL)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app("testing", instance_path=tmp)
        @app.get("/_help_demo_alarms")
        def demo_alarms():
            second = {**ROW, "id": "demo-record-2", "interface": "XGigabitEthernet0/0/23",
                      "note": "INC-DEMO-002: Sample investigation note"}
            return render_template("drilldown/alarms.html", rows=[ROW,second], source="eze",
                                   title="Demo - sample alarms",label="Sample congestion",
                                   scope="EZE",alarm_type="BANDWIDTH",date_range_label="All dates",
                                   date_from="",date_to="",date_from_display="",date_to_display="",
                                   default_ack_username="Demo Operator")
        @app.get("/_help_demo_mentor")
        def demo_mentor():
            return render_template("mentor/index.html",configured_sites=[dict(site_code="0460",
                                   site_name="DEMO SITE",province="Demo province",status="OK",
                                   source="Manual",added_at="11-Nov-2026 10:00")])
        @app.get("/_help_demo_blacklist")
        def demo_blacklist():
            return render_template("drilldown/_congestion_blacklist_rows.html",rules=[RULE])
        client=app.test_client()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel="msedge",headless=True)
            page=browser.new_page(viewport={"width":1600,"height":1000},device_scale_factor=1)
            errors=[]
            page.on("pageerror",lambda error:errors.append(str(error)))
            def respond(route):
                if route.request.method != "GET":
                    route.abort()
                    return
                parsed=urlsplit(route.request.url)
                if parsed.path=="/alarms/congestion/blacklist":
                    response=client.get("/_help_demo_blacklist")
                elif parsed.path.startswith("/static/") or parsed.path.startswith("/_help_demo_"):
                    response=client.get(parsed.path)
                else:
                    route.fulfill(status=200,body="{}",content_type="application/json")
                    return
                route.fulfill(status=response.status_code,body=response.data,content_type=response.content_type)
            page.route("**/*",respond)
            page.goto("http://demo.test/_help_demo_alarms",wait_until="networkidle")
            page.add_style_tag(content=".content{padding-top:30px!important} .alarm-table-wrap{max-height:500px!important}")
            page.locator("main.content").screenshot(path=str(OUT/"table-overview.png"))
            buttons=page.locator(".alarm-action-trigger")
            buttons.first.click()
            page.locator("main.content").screenshot(path=str(OUT/"action-menu.png"))
            page.locator(".alarm-action-menu.open button").filter(has_text="Acknowledge").click()
            page.locator("#ackTtIncWo").fill("INC-DEMO-001")
            page.locator("#ackNote").fill("Investigating port 22; carrier informed. Demo only.")
            page.locator("#ackModalOverlay .modal-content").screenshot(path=str(OUT/"acknowledge.png"))
            page.evaluate("closeAckModal()")
            buttons.first.click()
            page.locator(".alarm-action-menu.open [data-congestion-exclude]").click()
            page.locator("#congestionExcludeRemark").fill("Demo: approved monitoring exception for this interface only.")
            page.locator("#congestionExcludeModal .modal-content").screenshot(path=str(OUT/"exclude.png"))
            page.locator("#congestionExcludeModal [data-congestion-close]").first.click()
            page.locator(".alarm-actions [data-congestion-blacklist]").click()
            page.locator("#congestionBlacklistBody table").wait_for()
            page.locator("#congestionBlacklistModal .modal-content").screenshot(path=str(OUT/"blacklist.png"))
            page.locator("#congestionBlacklistBody .alarm-table-wrap").evaluate("e=>e.scrollLeft=e.scrollWidth")
            page.locator("#congestionBlacklistModal .modal-content").screenshot(path=str(OUT/"blacklist-restore.png"))
            page.locator("#congestionBlacklistModal [data-congestion-close]").click()
            buttons.first.click()
            page.locator(".alarm-action-menu.open button").filter(has_text="Clear Alarm").click()
            page.locator("#clearModalOverlay .modal-content").screenshot(path=str(OUT/"clear-alarm.png"))
            page.evaluate("closeClearModal()")
            search=page.locator(".table-search-input, #tableSearchInput, input[placeholder*='Search']").first
            if search.count():search.fill("0/0/22")
            page.locator("main.content").screenshot(path=str(OUT/"table-search.png"))
            page.goto("http://demo.test/_help_demo_mentor",wait_until="networkidle")
            page.locator("main.content").screenshot(path=str(OUT/"mentor-sites.png"))
            page.unroute_all(behavior="wait")
            browser.close()
            if errors:raise AssertionError(errors)
    print("Captured 9 real-UI demo screenshots. No POST requests, live source queries, or alert sends.")


if __name__=="__main__":capture()
