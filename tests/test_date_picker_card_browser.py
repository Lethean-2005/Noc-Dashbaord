"""The date calendar must stay in its filter card and preserve picked values."""
from pathlib import Path

import pytest
playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("width,height", [(1280,900), (360,480), (240,420)])
def test_calendar_stays_inside_card_on_desktop_and_small_screens(width, height):
    def field(name):
        return ('<div class="dp-field" data-date-picker><span class="dp-label">'+name+'</span>'
        '<button type="button" class="dp-trigger"><span class="dp-trigger-text">Select date</span></button>'
        '<input type="hidden" name="'+name+'"></div>')
    with playwright.sync_playwright() as runner:
        try:
            browser = runner.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Installed Edge is unavailable")
        page = browser.new_page(viewport={"width":width,"height":height})
        errors = []
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.set_content('<style>:root{--bg-card:white;--border-card:#ddd}body{margin:0}details{position:absolute;right:12px;top:30px}</style>'
            '<details class="date-filter"><summary>Filter by Occurred At</summary><form class="date-filter-form">'
            +field('from')+field('to')+'<div class="date-filter-actions"><button type="submit">Apply</button></div></form></details>')
        page.add_style_tag(path=str(ROOT/'app/static/css/components/tables.css'))
        page.evaluate("window.NocTime={parts:()=>({year:2026,month:11,day:17})}")
        page.add_script_tag(path=str(ROOT/'app/static/js/filter-dropdowns.js'))
        page.add_script_tag(path=str(ROOT/'app/static/js/date-picker.js'))
        page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
        page.locator('summary').click()
        page.locator('.dp-trigger').first.click()
        page.wait_for_function("document.querySelector('.date-filter-form').getBoundingClientRect().width >= Math.min(280,innerWidth-16)")
        bounds = page.locator('.date-filter-form').evaluate('(p)=>{const r=p.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,client:p.clientWidth,scroll:p.scrollWidth}}')
        assert bounds['left'] >= 7 and bounds['right'] <= width-7
        assert bounds['top'] >= 7 and bounds['bottom'] <= height-7
        assert bounds['scroll'] <= bounds['client']+1
        assert page.locator('.dp-popup').first.evaluate("p=>getComputedStyle(p).position") == 'static'
        popup = page.locator('.dp-popup').first
        popup.locator('.dp-nav').last.click()
        playwright.expect(popup.locator('.dp-month-label')).to_have_text('December 2026')
        popup.locator('.dp-nav').last.click()
        playwright.expect(popup.locator('.dp-month-label')).to_have_text('January 2027')
        popup.locator('.dp-day').filter(has_text='17').click()
        playwright.expect(page.locator('input[name=from]')).to_have_value('2027-01-17')
        page.locator('.dp-trigger').first.click()
        playwright.expect(popup.locator('.dp-day-selected')).to_have_text('17')
        page.keyboard.press('Escape')
        assert not page.locator('details').evaluate('p=>p.open')
        assert popup.is_hidden()
        page.locator('summary').click()
        assert popup.is_hidden()
        assert not errors
        browser.close()
