"""Browser regressions for circuit associations, report edits and popup retries."""
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as engine:
        try:
            instance = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Microsoft Edge is unavailable")
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    instance = browser.new_page()
    yield instance
    instance.close()


def load(page, name):
    page.add_script_tag(path=str(ROOT / "app/static/js" / name))


def test_circuit_rename_keeps_outage_data_and_deletion_removes_only_dependents(page):
    page.set_content('<table><tbody id="irCircuitsRows"><tr><td><input name="circuit_id" value="A"></td></tr><tr><td><input name="circuit_id" value="B"></td></tr></tbody></table><table><tbody id="irOutageRows"><tr><td><input name="outage_circuit" value="B"><input name="outage_jan" value="99.9%"></td></tr></tbody></table><table><tbody id="irServicesOutageRows"><tr><td><input name="outage_circuit_id" value="B"></td></tr></tbody></table>')
    load(page, "smart-circuits.js")
    page.locator('[name=circuit_id]').nth(1).fill("B-NEW")
    playwright.expect(page.locator('[name=outage_circuit]')).to_have_value("B-NEW")
    playwright.expect(page.locator('[name=outage_circuit_id]')).to_have_value("B-NEW")
    playwright.expect(page.locator('[name=outage_jan]')).to_have_value("99.9%")
    page.locator('[name=circuit_id]').nth(1).fill("")
    playwright.expect(page.locator('[name=outage_circuit]')).to_have_value("")
    playwright.expect(page.locator('[name=outage_jan]')).to_have_value("99.9%")
    page.locator('[name=circuit_id]').nth(1).fill("B-FINAL")
    playwright.expect(page.locator('[name=outage_circuit]')).to_have_value("B-FINAL")
    page.locator('[name=outage_circuit]').select_option("A")
    page.locator('[name=circuit_id]').first.fill("A-NEW")
    playwright.expect(page.locator('[name=outage_circuit]')).to_have_value("A-NEW")
    page.evaluate("document.querySelector('#irCircuitsRows tr:last-child').remove()")
    playwright.expect(page.locator('#irServicesOutageRows tr')).to_have_count(0)
    playwright.expect(page.locator('[name=outage_circuit]')).to_have_value("A-NEW")
    playwright.expect(page.locator('select')).to_have_count(0)


def test_report_row_removal_warns_without_marking_initial_render_dirty(page):
    page.set_content('<form id="incidentReportForm"><div class="ir-event-row"><input value="existing"><button class="ir-event-remove" type="button" onclick="this.parentElement.remove()">Delete</button></div></form>')
    source = (ROOT / "app/static/js/incident-report.js").read_text(encoding="utf-8")
    page.add_script_tag(content=source[:source.index("})();") + 5])
    check = "() => {const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}"
    assert page.evaluate(check) is False
    page.locator('button').click()
    assert page.evaluate(check) is True
    page.evaluate("document.dispatchEvent(new Event('submit'))")
    assert page.evaluate(check) is False


def test_weekday_popup_retries_after_http_error(page):
    page.set_content('<button data-day-modal="volumeDayCategoryModal_0">Open</button><div id="volumeDayCategoryModal_0" data-day-index="0"><div class="volume-day-popup-body"></div></div>')
    page.evaluate("window.fixtureResponseOk=false;window.fetch=async()=>({ok:window.fixtureResponseOk,text:async()=>'<p>Loaded incident details</p>'})")
    load(page, "graph_cards.js")
    page.locator('button').click()
    playwright.expect(page.locator('.volume-day-popup-body')).to_contain_text("reopen to retry")
    assert page.locator('#volumeDayCategoryModal_0').get_attribute('data-loaded') is None
    page.evaluate('window.fixtureResponseOk=true')
    page.locator('button').click()
    playwright.expect(page.locator('.volume-day-popup-body')).to_contain_text("Loaded incident details")
    playwright.expect(page.locator('#volumeDayCategoryModal_0')).to_have_attribute('data-loaded', '1')


def test_new_report_tables_preserve_unknown_circuits_in_draft_data(page):
    page.set_content('<form><table><tbody id="irCircuitsRows"><tr><td><input name="circuit_id" value="A"></td></tr><tr><td><input name="circuit_id" value="B"></td></tr></tbody></table><table><tbody id="irFailureRows"><tr><td><input name="react_circuit_id" value="OLD"><input name="react_ticket_no" value="Saved row"></td></tr></tbody></table><table><tbody id="irCreditRows"><tr><td><input name="credit_circuit" value="B"></td></tr></tbody></table></form>')
    load(page, "smart-circuits.js")
    playwright.expect(page.locator('[name=react_circuit_id]')).to_have_value("OLD")
    assert page.evaluate("new FormData(document.querySelector('form')).get('react_circuit_id')") == "OLD"
    assert page.locator('[name=react_circuit_id]').evaluate('(field) => field.validity.valid') is False
    page.locator('[name=react_circuit_id]').select_option('B')
    page.locator('[name=circuit_id]').nth(1).fill('RENAMED')
    playwright.expect(page.locator('[name=react_circuit_id]')).to_have_value('RENAMED')
    playwright.expect(page.locator('[name=credit_circuit]')).to_have_value('RENAMED')
    page.evaluate("document.querySelector('#irCircuitsRows tr:last-child').remove()")
    playwright.expect(page.locator('#irFailureRows tr')).to_have_count(0)
    playwright.expect(page.locator('#irCreditRows tr')).to_have_count(0)
