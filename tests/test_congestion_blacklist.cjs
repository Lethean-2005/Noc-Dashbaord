const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    const handlers = {}, pending = [];
    const body = { textContent: '', innerHTML: '', querySelectorAll: () => [] };
    const modal = { style: {}, querySelector: () => null };
    const document = {
        addEventListener(type, fn) { handlers[type] = fn; },
        getElementById(id) { return id === 'congestionBlacklistBody' ? body : modal; }
    };
    const fetch = (url, options) => new Promise(resolve => pending.push({resolve, options}));
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/congestion-blacklist.js'), 'utf8'), {
        document, fetch, AbortController, location: { pathname: '/congestion', search: '' }
    });
    const button = { isConnected: true, focus() {}, closest: () => null };
    function open() {
        handlers.click({ target: { closest: s => s === '[data-congestion-blacklist]' ? button : null } });
    }
    function close() {
        modal.id = 'congestionBlacklistModal';
        handlers.click({ target: { closest: s => s === '[data-congestion-close]' ? { closest: () => modal } : null } });
    }
    return { pending, body, open, close };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('latest blacklist request wins even when an old response ignores cancellation', async () => {
    const state = setup();
    state.open();
    state.open();
    assert.equal(state.pending[0].options.signal.aborted, true);
    assert.equal(state.pending[1].options.cache, 'no-store');
    state.pending[1].resolve({ ok: true, text: async () => 'latest' });
    await settle();
    state.pending[0].resolve({ ok: true, text: async () => 'stale' });
    await settle();
    assert.equal(state.body.innerHTML, 'latest');
});

test('closing the blacklist cancels its request and ignores a late response', async () => {
    const state = setup();
    state.open();
    state.close();
    assert.equal(state.pending[0].options.signal.aborted, true);
    state.pending[0].resolve({ ok: true, text: async () => 'late' });
    await settle();
    assert.equal(state.body.innerHTML, '');
});
