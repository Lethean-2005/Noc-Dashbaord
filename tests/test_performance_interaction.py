"""Pointer and table interactions must avoid repeated work and retain all rows."""
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def page():
    with playwright.sync_playwright() as runner:
        try:
            browser = runner.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Microsoft Edge is unavailable")
        page = browser.new_page()
        yield page
        browser.close()


def track_tooltip_writes(page):
    page.evaluate("""() => {
        const tip=document.getElementById('perfTooltip');
        const property=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
        window.tipWrites=0;
        Object.defineProperty(tip,'innerHTML', {
            get(){ return property.get.call(this); },
            set(value){ window.tipWrites++; property.set.call(this,value); }
        });
    }""")


def test_tooltip_batches_pointer_updates_escapes_names_and_cancels_on_scroll(page):
    page.set_content('<div id="perfTooltip"></div><div class="expenses-bar-site-down" data-site-code="TEST" data-total="5"></div>')
    page.locator('.expenses-bar-site-down').evaluate("e => e.dataset.siteName='Site <img id=unsafe-image src=invalid>'")
    page.locator('.expenses-bar-site-down').evaluate("e=>e.dataset.durations=JSON.stringify([{label: '0-4h', count:5}])")
    track_tooltip_writes(page)
    page.add_script_tag(path=str(Path('app/static/js/performance.js').resolve()))
    result=page.evaluate("""async () => {
        const bar=document.querySelector('.expenses-bar-site-down');
        for(let i=0;i<100;i++) bar.dispatchEvent(new MouseEvent('mousemove',{clientX:100+i,clientY:100}));
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        const tip=document.getElementById('perfTooltip');
        return {writes:window.tipWrites,left:tip.style.left,shown:tip.classList.contains('show'),text:tip.textContent};
    }""")
    assert result['writes']==1 and result['left']=='199px' and result['shown']
    assert 'Site <img' in result['text'] and page.locator('#unsafe-image').count()==0
    cancelled=page.evaluate("""async () => {
        document.querySelector('.expenses-bar-site-down').dispatchEvent(new MouseEvent('mousemove',{clientX:300,clientY:100}));
        document.dispatchEvent(new Event('scroll'));
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        return {writes:window.tipWrites,shown:document.getElementById('perfTooltip').classList.contains('show')};
    }""")
    assert cancelled=={'writes':1,'shown':False}


def test_donut_tooltip_reuses_content_and_closes_on_resize(page):
    page.set_content('<div id="perfTooltip"></div><div id="donutSiteDown" data-total="5"></div>')
    page.locator('#donutSiteDown').evaluate("e=>e.dataset.categories=JSON.stringify([{category:'Power',count:5,pct:100,note:'Verified note'}])")
    track_tooltip_writes(page)
    page.add_script_tag(path=str(Path('app/static/js/performance.js').resolve()))
    writes=page.evaluate("""async () => {
        const circle=document.querySelector('.perf-donut-segment');
        for(let i=0;i<100;i++)circle.dispatchEvent(new MouseEvent('mousemove',{clientX:100+i,clientY:100}));
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        return window.tipWrites;
    }""")
    assert writes==1
    playwright.expect(page.locator('#perfTooltip')).to_contain_text('Verified note')
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    assert not page.locator('#perfTooltip').evaluate("e=>e.classList.contains('show')")


def test_search_works_after_notice_and_preserves_blank_cells_icons_and_added_rows(page):
    page.set_content('<div class="alarm-header"><span class="alarm-row-count">1000 records</span></div><div class="row-cap-notice">All records remain available.</div><div class="alarm-table-wrap"><table class="alarm-table"><tbody>'
        + ''.join(f'<tr><td>Record {i}</td><td> </td><td><button><svg></svg></button></td></tr>' for i in range(1000))
        + '</tbody></table></div>')
    page.add_script_tag(path=str(Path('app/static/js/table.js').resolve()))
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    search=page.locator('.alarm-search')
    search.fill('record 99')
    playwright.expect(page.locator('.alarm-row-count')).to_have_text('11 records')
    assert page.locator('tbody tr:not(.empty-row)').count()==1000
    assert page.locator('tbody tr').first.locator('td').nth(1).inner_text()=='\u2014'
    assert page.locator('tbody svg').count()==1000
    page.evaluate("""() => {
        document.querySelector('tbody').insertAdjacentHTML('beforeend','<tr><td>Record 1000</td><td></td><td></td></tr>');
        window.NocTableSearch(document.querySelector('.alarm-table-wrap'));
    }""")
    search.fill('')
    playwright.expect(page.locator('.alarm-row-count')).to_have_text('1001 records')
    assert page.locator('.search-empty-row').count()==1
