"""Deferred charts must load, retry and keep working after filter swaps."""
import re
from urllib.parse import urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")


def test_deferred_charts_retry_and_filter_without_page_errors(app):
    with playwright.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Microsoft Edge is unavailable")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors, chart_queries = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        client = app.test_client()

        def respond(route):
            parsed = urlsplit(route.request.url)
            if parsed.hostname != "dashboard.test" or route.request.method != "GET":
                route.abort()
                return
            path = parsed.path + (("?" + parsed.query) if parsed.query else "")
            if parsed.path == "/performance-cards":
                chart_queries.append(parsed.query)
                if len(chart_queries) == 1:
                    route.fulfill(status=503, body="Temporary failure")
                    return
            response = client.get(path)
            headers = dict(response.headers)
            headers.pop("Content-Length", None)
            route.fulfill(status=response.status_code, headers=headers, body=response.data)

        page.route("**/*", respond)
        try:
            page.goto("http://dashboard.test/?response_time_category=Power", wait_until="networkidle")
            section = page.locator("#performanceSection")
            section.scroll_into_view_if_needed()
            retry = section.locator("[data-retry-performance]")
            playwright.expect(retry).to_be_visible()
            retry.click()
            playwright.expect(section.locator("#perfTooltip")).to_have_count(1)
            playwright.expect(section).not_to_have_attribute("data-lazy-url", ".+")
            assert "response_time_category=Power" in chart_queries[-1]
            details = section.locator("details.date-filter").first
            details.locator("summary").click()
            details.locator('input[type="checkbox"][name="duration_bucket"]').first.check()
            details.locator('button[type="submit"]').click()
            playwright.expect(page).to_have_url(re.compile("duration_bucket="))
            playwright.expect(section.locator("#perfTooltip")).to_have_count(1)
            section.evaluate("node => node.setAttribute('aria-busy', 'true')")
            assert page.evaluate('isUserBusy()') is True
            section.evaluate("node => node.removeAttribute('aria-busy')")
            assert len(chart_queries) == 3
            assert "response_time_category=Power" in chart_queries[-1]
            assert errors == []
        finally:
            browser.close()


def test_filter_popup_scrolling_avoids_remeasurement_and_stays_in_viewport():
    from pathlib import Path

    with playwright.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Microsoft Edge is unavailable")
        page = browser.new_page(viewport={"width": 800, "height": 600})
        try:
            page.set_content('<style>html,body{margin:0;height:100%}#main-wrapper{height:100%;overflow:auto}.date-filter{margin-top:150px;margin-left:300px}.date-filter-form{box-sizing:border-box;display:flex;flex-direction:column;background:white;width:260px;padding:12px;border:1px solid #ccc}.filter-panel-floating{position:fixed;inset:auto;margin:0;overflow:auto}.category-filter-options{height:220px;min-height:0;overflow:auto;overscroll-behavior:contain}label{display:block;height:28px}</style><div id="main-wrapper"><details class="date-filter"><summary>Filter</summary><form class="date-filter-form"><div class="category-filter-options">'+''.join('<label><input type="checkbox">Choice '+str(i)+'</label>' for i in range(60))+'</div><div class="date-filter-actions"><button type="submit">Apply</button></div></form></details><div style="height:1600px"></div></div>')
            page.evaluate("""() => {
                window.panelMeasurements=0;
                const original=Element.prototype.getBoundingClientRect;
                Element.prototype.getBoundingClientRect=function(){
                    if(this.classList.contains('date-filter-form')) window.panelMeasurements++;
                    return original.call(this);
                };
                document.querySelector('form').addEventListener('submit',event=>event.preventDefault());
            }""")
            page.add_script_tag(path=str(Path('app/static/js/filter-dropdowns.js').resolve()))
            page.locator('summary').click()
            playwright.expect(page.locator('form')).to_be_visible()
            page.wait_for_timeout(80)
            measured=page.evaluate('window.panelMeasurements')
            assert measured == 1
            page.evaluate("document.querySelector('.category-filter-options').scrollTop=150")
            page.wait_for_timeout(80)
            assert page.evaluate('window.panelMeasurements') == measured
            page.evaluate("document.querySelector('#main-wrapper').scrollTop=70")
            page.wait_for_timeout(80)
            assert page.evaluate('window.panelMeasurements') == measured
            bounds=page.locator('form').bounding_box()
            assert 0 <= bounds['y'] and bounds['y']+bounds['height'] <= 600
            page.set_viewport_size({'width': 360, 'height': 360})
            page.wait_for_timeout(100)
            resized = page.locator('form').bounding_box()
            assert resized['x'] >= 0 and resized['x'] + resized['width'] <= 360
            assert resized['y'] >= 0 and resized['y'] + resized['height'] <= 360
            page.locator('button').click()
            playwright.expect(page.locator('details')).not_to_have_attribute('open', '')
            assert not page.locator('form').evaluate("node=>node.matches(':popover-open')")
        finally:
            browser.close()


def test_table_search_skips_unchanged_visibility_and_keeps_all_rows():
    from pathlib import Path

    with playwright.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Microsoft Edge is unavailable")
        page = browser.new_page()
        try:
            page.set_content('<div class="alarm-header"><span class="alarm-row-count">1000 records</span></div>'
                             '<div class="alarm-table-wrap"><table class="alarm-table"><tbody>'
                             + ''.join(f'<tr><td>Record {i}</td></tr>' for i in range(1000))
                             + '</tbody></table></div>')
            page.add_script_tag(path=str(Path("app/static/js/table.js").resolve()))
            page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
            search = page.locator('.alarm-search')
            search.fill('record 99')
            playwright.expect(page.locator('.alarm-row-count')).to_have_text('11 records')
            page.evaluate("""() => {
                window.rowChanges = 0;
                new MutationObserver(items => window.rowChanges += items.length)
                    .observe(document.querySelector('tbody'), {subtree: true, attributes: true, attributeFilter: ['style']});
            }""")
            search.fill(' RECORD 99 ')
            page.wait_for_timeout(200)
            assert page.evaluate('window.rowChanges') == 0
            search.fill('')
            playwright.expect(page.locator('.alarm-row-count')).to_have_text('1000 records')
            assert page.locator('tbody tr:not(.empty-row)').count() == 1000
        finally:
            browser.close()
