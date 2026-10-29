const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..', '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('website uses the canonical token for active API requests and safe session metadata', () => {
  const source = read('docs/main.js');
  assert.equal(source.includes("localStorage.getItem(TOKEN_KEY)"), true);
  assert.equal(source.includes('localStorage.setItem(tokenStorageKey'), false);
  assert.equal(source.includes('localStorage.getItem(tokenStorageKey'), false);
  assert.equal(source.includes('localStorage.removeItem(TOKEN_KEY)'), true);
  assert.equal(source.includes('localStorage.removeItem(preferencesCacheKey)'), true);
  const sessionStart = source.indexOf('function persistSession');
  const sessionEnd = source.indexOf('function clearSession');
  const sessionSource = source.slice(sessionStart, sessionEnd);
  assert.equal(sessionSource.includes('authState.set({'), true);
  const metadataStart = sessionSource.indexOf('authState.set({');
  const metadataEnd = sessionSource.indexOf('});', metadataStart);
  const metadataSource = sessionSource.slice(metadataStart, metadataEnd);
  assert.equal(metadataSource.includes('token'), false);
});

test('legacy website migration validates preferences before adopting a token', () => {
  const source = read('docs/main.js');
  assert.equal(source.includes("const LEGACY_TOKEN_KEYS = ['isweep-token', 'isweepToken'];"), true);
  assert.equal(source.includes('async function validateToken(token)'), true);
  assert.equal(source.includes('`${getBackendUrl()}/preferences`'), true);
  assert.equal(source.includes('async function migrateLegacySession()'), true);
  assert.equal(source.includes('clearSession({ markLoggedOut: true })'), true);
});

test('retired filter sync guard cannot install a second save or token handler', () => {
  const source = read('docs/filter_sync_guard.js');
  assert.equal(source.includes('addEventListener'), false);
  assert.equal(source.includes('/preferences'), false);
  const filterHtml = read('docs/Filter.html');
  assert.equal(filterHtml.includes('filter_sync_guard.js'), false);
});

test('website bridge delegates token validation and forwards a sanitized user id', () => {
  const source = read('ISweep_extention/site_token_bridge.js');
  assert.equal(source.includes("const USER_ID_KEY = 'isweep-user-id';"), true);
  assert.equal(source.includes('userId: window.localStorage.getItem(USER_ID_KEY) || null'), true);
  assert.equal(source.includes('token,'), true);
  assert.equal(source.includes('chrome.storage.local.set({ [TOKEN_KEY]: token })'), false);
  assert.equal(source.includes('console.log'), true);
});

test('development caption token remains isolated from the canonical account token', () => {
  const source = read('ISweep_extention/background.js');
  assert.equal(source.includes("'isweepLocalCaptionToken'"), true);
  assert.equal(source.includes("const TOKEN_KEY = 'isweep_auth_token'"), true);
});
