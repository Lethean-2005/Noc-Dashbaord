const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
test('Cambodia wall clock uses UTC+7 across a date boundary', () => {
  const window = {};
  vm.runInNewContext(fs.readFileSync('app/static/js/cambodia-time.js','utf8'), {window,Intl,Date});
  const p = window.NocTime.parts(new Date('2026-11-05T20:30:00Z'));
  assert.equal(p.day,6); assert.equal(p.hour,3); assert.equal(p.minute,30);
});
