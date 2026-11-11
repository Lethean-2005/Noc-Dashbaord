const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
    const handlers = {};
    const filters = [];
    const document = {
        addEventListener(name, callback) { handlers[name] = callback; },
        querySelectorAll() { return filters; }
    };
    function addFilter(open) {
        const summary = { focused: false, focus() { this.focused = true; } };
        const filter = { open, matches: () => true, querySelector: () => summary, summary };
        filters.push(filter);
        return filter;
    }
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/filter-dropdowns.js'), 'utf8'), { document, window: { addEventListener() {} } });
    return { handlers, addFilter };
}

test('clicking another filter closes the first before native opening', () => {
    const { handlers, addFilter } = setup();
    const first = addFilter(true), second = addFilter(false);
    handlers.click({ target: { closest: () => second } });
    assert.equal(first.open, false);
    assert.equal(second.open, false); // native summary click still controls opening
});

test('outside click closes the dropdown', () => {
    const { handlers, addFilter } = setup();
    const filter = addFilter(true);
    handlers.click({ target: { closest: () => null } });
    assert.equal(filter.open, false);
});

test('clicking checkbox or input inside a filter keeps it open', () => {
    const { handlers, addFilter } = setup();
    const filter = addFilter(true);
    handlers.click({ target: { closest: () => filter } });
    assert.equal(filter.open, true);
});

test('opening an AJAX-added filter closes existing filters', () => {
    const { handlers, addFilter } = setup();
    const first = addFilter(true), inserted = addFilter(true);
    handlers.toggle({ target: inserted });
    assert.equal(first.open, false);
    assert.equal(inserted.open, true);
});

test('Escape closes the dropdown and returns focus to its button', () => {
    const { handlers, addFilter } = setup();
    const filter = addFilter(true);
    let prevented = false;
    handlers.keydown({ key: 'Escape', preventDefault() { prevented = true; } });
    assert.equal(filter.open, false);
    assert.equal(filter.summary.focused, true);
    assert.equal(prevented, true);
});

test('a delayed close event does not close the newly opened filter', () => {
    const { handlers, addFilter } = setup();
    const oldFilter = addFilter(false), current = addFilter(true);
    handlers.toggle({ target: oldFilter });
    assert.equal(current.open, true);
});
