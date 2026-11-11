const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
    const pending = [], errors = [], changes = [];
    const target = { innerHTML: 'original', attrs: {}, setAttribute(k,v) { this.attrs[k]=v; }, removeAttribute(k) { delete this.attrs[k]; } };
    const window = { location: { pathname: '/', search: '?volume_category=Power&response_time_category=Site+Down', hash: '' }, history: { replaceState(a,b,url) { changes.push(url); window.location.search = url.includes('?') ? url.slice(url.indexOf('?')) : ''; } }, showModal(title,message) { errors.push(message); } };
    class FakeFormData { constructor(form) { this.form=form; } getAll(name) { return this.form.values[name] || []; } }
    const document = { querySelector() { return target; } };
    const fetch = (url, options) => new Promise(resolve => pending.push({ resolve, url, options }));
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/dashboard-fragments.js'), 'utf8'), { window, document, fetch, AbortController, URLSearchParams, FormData: FakeFormData });
    return { api: window.NocDashboardFragments, pending, errors, changes, target };
}

test('newer filter response wins even if an older request ignores abort', async () => {
    const { api, pending, target, changes } = setup();
    const old = api.replace({ selector: '#cards', url: '/cards?old', search: '?old' });
    const current = api.replace({ selector: '#cards', url: '/cards?new', search: '?new' });
    assert.equal(pending[0].options.signal.aborted, true);
    pending[1].resolve({ ok: true, text: async () => 'new cards' });
    await current;
    pending[0].resolve({ ok: true, text: async () => 'old cards' });
    await old;
    assert.equal(target.innerHTML, 'new cards');
    assert.deepEqual(changes, ['/?new=']);
    assert.equal(target.attrs['aria-busy'], undefined);
});

test('failed response leaves existing cards intact and shows an error', async () => {
    const { api, pending, target, errors } = setup();
    const request = api.replace({ selector: '#cards', url: '/cards', search: '' });
    pending[0].resolve({ ok: false });
    await request;
    assert.equal(target.innerHTML, 'original');
    assert.equal(errors.length, 1);
    assert.equal(target.attrs['aria-busy'], undefined);
});

test('Apply preserves other cards current filters instead of stale hidden fields', () => {
    const { api } = setup();
    const form = { elements: [{ name: 'volume_category', type: 'checkbox' }, { name: 'response_time_category', type: 'hidden' }], values: { volume_category: ['Facility'], response_time_category: ['OLD'] } };
    const params = new URLSearchParams(api.searchForForm(form));
    assert.equal(params.get('volume_category'), 'Facility');
    assert.equal(params.get('response_time_category'), 'Site Down');
});

test('Clear removes only this dropdown selections', () => {
    const { api } = setup();
    const form = { elements: [{ name: 'volume_category', type: 'checkbox' }], values: {} };
    const params = new URLSearchParams(api.searchForForm(form, true));
    assert.equal(params.has('volume_category'), false);
    assert.equal(params.get('response_time_category'), 'Site Down');
});


test('concurrent sections preserve both filter changes in the URL', async () => {
    const { api, pending, changes } = setup();
    const a = api.replace({selector: '#graph', url: '/a', search: '?volume_category=Facility&response_time_category=Site+Down'});
    const b = api.replace({selector: '#performance', url: '/b', search: '?volume_category=Power&response_time_category=Power'});
    pending[0].resolve({ok:true, text:async()=> 'graph'});
    await a;
    assert.ok(changes[0].includes('volume_category=Facility'));
    pending[1].resolve({ok:true, text:async()=> 'performance'});
    await b;
    const result = new URLSearchParams(changes.at(-1).slice(1));
    assert.equal(result.get('volume_category'), 'Facility');
    assert.equal(result.get('response_time_category'), 'Power');
});
