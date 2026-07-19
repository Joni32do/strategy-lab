/* node test for the skins keystone. Run: node test/skins.js (from repo root) */
'use strict';

var Skins = require('../js/skins/registry.js');
var SkinChrome = require('../js/skin-chrome.js');

var pass = 0, fail = 0;

function ok(name, cond) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name); }
}

function eq(name, got, want) {
  ok(name + ' (got ' + JSON.stringify(got) + ', want ' + JSON.stringify(want) + ')',
     JSON.stringify(got) === JSON.stringify(want));
}

/* ---------- registry ---------- */
Skins.register({ id: 'original', name: 'Original' });
Skins.register({ id: 'minimal', name: 'Minimal' });

ok('registry.has original', Skins.has('original') === true);
ok('registry.has missing', Skins.has('nope') === false);
ok('registry.get returns object', Skins.get('minimal') && Skins.get('minimal').name === 'Minimal');
ok('registry.get missing undefined', Skins.get('nope') === undefined);
eq('registry.list order', Skins.list(), [
  { id: 'original', name: 'Original' },
  { id: 'minimal', name: 'Minimal' }
]);

// duplicate id replaces, does not duplicate
Skins.register({ id: 'minimal', name: 'Minimal v2' });
eq('registry duplicate replaces', Skins.list(), [
  { id: 'original', name: 'Original' },
  { id: 'minimal', name: 'Minimal v2' }
]);
ok('registry list length unchanged', Skins.list().length === 2);

/* ---------- resolveSkin precedence ---------- */
var R = SkinChrome.resolveSkin;
var av = ['original', 'minimal', 'neon'];

eq('resolve: url wins',
   R({ url: 'neon', stored: 'minimal', server: 'original', available: av }), 'neon');
eq('resolve: stored wins over server (no url)',
   R({ url: null, stored: 'minimal', server: 'original', available: av }), 'minimal');
eq('resolve: server used when no url/stored',
   R({ url: null, stored: null, server: 'neon', available: av }), 'neon');
eq('resolve: url not in available ignored, falls to stored',
   R({ url: 'ghost', stored: 'minimal', server: 'original', available: av }), 'minimal');
eq('resolve: stored not in available ignored, falls to server',
   R({ url: null, stored: 'ghost', server: 'original', available: av }), 'original');
eq('resolve: nothing valid -> available[0]',
   R({ url: 'x', stored: 'y', server: 'z', available: av }), 'original');
eq('resolve: empty available -> original',
   R({ url: 'x', stored: 'y', server: 'z', available: [] }), 'original');
eq('resolve: no args -> original', R({}), 'original');

/* ---------- summary ---------- */
console.log('');
console.log('----------------------------------------');
console.log('Skins keystone: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
