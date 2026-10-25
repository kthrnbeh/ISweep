const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadPopupHooks(clock = null) {
  const source = fs.readFileSync(path.resolve(__dirname, '..', 'popup.js'), 'utf8');
  const context = {
    console: { log() {}, warn() {}, error() {} },
    document: { getElementById: () => null, addEventListener() {} },
    chrome: {
      storage: { local: { get: async () => ({}), set: async () => {}, remove: async () => {} } },
      tabs: { query: async () => (clock ? [{ id: 1 }] : []), sendMessage: async () => clock || ({}) },
      runtime: { sendMessage: async () => ({}) },
    },
    URL,
    alert() {},
    setTimeout,
    clearTimeout,
    globalThis: {},
    __ISWEEP_TEST_MODE__: true,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'popup.js' });
  return context.__ISWEEP_POPUP_TEST_HOOKS__;
}

test('popup parses YouTube-style MM:SS and total seconds', () => {
  const hooks = loadPopupHooks();
  assert.equal(hooks.parsePlaybackTime('1:15'), 75);
  assert.equal(hooks.parsePlaybackTime('1:16'), 76);
  assert.equal(hooks.parsePlaybackTime('75'), 75);
  assert.equal(hooks.parsePlaybackTime('1:02:03.5'), 3723.5);
});

test('popup rejects invalid playback times and formats timestamps for humans', () => {
  const hooks = loadPopupHooks();
  assert.equal(hooks.parsePlaybackTime('1:60'), null);
  assert.equal(hooks.parsePlaybackTime('-1'), null);
  assert.equal(hooks.parsePlaybackTime('one minute'), null);
  assert.equal(hooks.parsePlaybackTime('1:2:3:4'), null);
  assert.equal(hooks.formatPlaybackTime(72.93), '1:12.93');
  assert.equal(hooks.formatPlaybackTime(3723.5), '1:02:03.50');
});

test('popup captures the active YouTube video clock in a human-friendly field', async () => {
  const hooks = loadPopupHooks({ ok: true, video_id: 'tQmEd_UeeIk', current_time: 75.25 });
  const input = { value: '' };
  assert.equal(await hooks.captureCurrentVideoTime(input), true);
  assert.equal(input.value, '1:15.25');
});
