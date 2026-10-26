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

test('popup groups replay attempts without combining distinct occurrences', () => {
  const hooks = loadPopupHooks();
  const groups = hooks.groupLearningEvents([
    { event_id: 3, video_id: 'video-1', matched_word: 'hell', predicted_start_seconds: 53.62, predicted_end_seconds: 54.0 },
    { event_id: 2, video_id: 'video-1', matched_word: 'hell', predicted_start_seconds: 53.7, predicted_end_seconds: 54.1 },
    { event_id: 1, video_id: 'video-1', matched_word: 'hell', predicted_start_seconds: 80.0, predicted_end_seconds: 80.4 },
  ]);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].attempts.length, 2);
  assert.equal(groups[1].attempts.length, 1);
});

test('popup only treats a feedback-bearing event as removable and explains delete failures', () => {
  const hooks = loadPopupHooks();
  assert.equal(hooks.hasSavedFeedback({ event_id: 1 }), false);
  assert.equal(hooks.hasSavedFeedback({ event_id: 2, feedback: { result: 'early' } }), true);
  assert.match(hooks.learningFeedbackErrorMessage({ status: 401 }, 'remove'), /session expired/);
  assert.match(hooks.learningFeedbackErrorMessage({ status: 404 }, 'remove'), /mute event was kept/);
  assert.match(hooks.learningFeedbackErrorMessage({ error: 'backend_unavailable' }, 'remove'), /backend is unavailable/);
});

test('popup keeps review states separate and exposes review actions for grouped occurrences', () => {
  const hooks = loadPopupHooks();
  const groups = hooks.groupLearningEvents([
    { event_id: 1, video_id: 'video-1', matched_word: 'hell', predicted_start_seconds: 10, predicted_end_seconds: 10.4, review_state: 'active' },
    { event_id: 2, video_id: 'video-1', matched_word: 'hell', predicted_start_seconds: 10, predicted_end_seconds: 10.4, review_state: 'excluded' },
  ]);
  assert.equal(groups.length, 2);
  const active = groups.find((group) => group.representative.review_state !== 'excluded');
  const excluded = groups.find((group) => group.representative.review_state === 'excluded');
  assert.deepEqual(Array.from(active.attempts, (event) => event.event_id), [1]);
  assert.deepEqual(Array.from(excluded.attempts, (event) => event.event_id), [2]);
});

test('popup keeps every saved correction discoverable when feedback is not on the representative attempt', () => {
  const hooks = loadPopupHooks();
  const groups = hooks.groupLearningEvents([
    { event_id: 10, video_id: 'video-2', matched_word: 'hell', predicted_start_seconds: 20, predicted_end_seconds: 20.4 },
    { event_id: 9, video_id: 'video-2', matched_word: 'hell', predicted_start_seconds: 20, predicted_end_seconds: 20.4, feedback: { result: 'early', corrected_start_seconds: 21, corrected_end_seconds: 21.4 } },
    { event_id: 8, video_id: 'video-2', matched_word: 'hell', predicted_start_seconds: 20, predicted_end_seconds: 20.4, feedback: { result: 'late', corrected_start_seconds: 22, corrected_end_seconds: 22.4 } },
    { event_id: 7, video_id: 'video-2', matched_word: 'hell', predicted_start_seconds: 20, predicted_end_seconds: 20.4, review_state: 'excluded', feedback: { result: 'correct', corrected_start_seconds: 20, corrected_end_seconds: 20.4 } },
  ]);
  assert.equal(groups.length, 2);
  const active = groups.find((group) => group.representative.review_state !== 'excluded');
  assert.equal(active.representative.event_id, 9);
  assert.deepEqual(Array.from(active.savedCorrections, (event) => event.event_id), [9, 8]);
  assert.deepEqual(Array.from(active.attempts, (event) => event.event_id), [10, 9, 8]);
  const excluded = groups.find((group) => group.representative.review_state === 'excluded');
  assert.deepEqual(Array.from(excluded.savedCorrections, (event) => event.event_id), [7]);
});
