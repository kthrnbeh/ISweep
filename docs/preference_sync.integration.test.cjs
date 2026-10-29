const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const mainSource = fs.readFileSync(path.join(root, 'docs', 'main.js'), 'utf8');
const start = mainSource.indexOf('async function persistPreferences');
const end = mainSource.indexOf('async function fetchAndCachePreferences', start);
const persistSource = mainSource.slice(start, end);

function loadPersistPreferences(fetchImpl) {
  const local = new Map([['isweep_auth_token', 'test-token']]);
  let cached = null;
  const context = {
    TOKEN_KEY: 'isweep_auth_token',
    localStorage: {
      getItem: (key) => local.get(key) || null,
      setItem: (key, value) => local.set(key, String(value)),
      removeItem: (key) => local.delete(key),
    },
    fetch: fetchImpl,
    getBackendUrl: () => 'http://127.0.0.1:5000',
    cachePreferences: (value) => { cached = value; },
    console: { log() {}, warn() {} },
  };
  vm.runInNewContext(`${persistSource}; globalThis.persistPreferences = persistPreferences;`, context);
  return { persistPreferences: context.persistPreferences, getCached: () => cached };
}

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

test('one save request accepts the backend canonical hell selection', async () => {
  const calls = [];
  const { persistPreferences, getCached } = loadPersistPreferences(async (url, options) => {
    calls.push({ url, options });
    return response({ blocklist: { items: ['hell'] } });
  });

  const result = await persistPreferences({ blocklist: { items: ['hell'] } });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, 'PUT');
  assert.deepEqual(result.prefs.blocklist.items, ['hell']);
  assert.deepEqual(getCached().blocklist.items, ['hell']);
});

test('save rejects a successful response without canonical blocklist.items', async () => {
  const { persistPreferences, getCached } = loadPersistPreferences(async () => response({ categories: {} }));

  await assert.rejects(
    persistPreferences({ blocklist: { items: ['hell'] } }),
    /canonical blocklist\.items/
  );
  assert.equal(getCached(), null);
});

test('save rejects a backend response that loses the selected word', async () => {
  const { persistPreferences, getCached } = loadPersistPreferences(async () => (
    response({ blocklist: { items: [] } })
  ));

  await assert.rejects(
    persistPreferences({ blocklist: { items: ['hell'] } }),
    /different selected-word list/
  );
  assert.equal(getCached(), null);
});

test('empty save refuses to replace an existing non-empty backend selection', async () => {
  const calls = [];
  const { persistPreferences } = loadPersistPreferences(async (url, options) => {
    calls.push({ url, options });
    if (options?.method === 'GET') return response({ blocklist: { items: ['hell'] } });
    return response({ blocklist: { items: [] } });
  });

  await assert.rejects(
    persistPreferences({ blocklist: { items: [] } }),
    /Refusing to replace existing selected words/
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, 'GET');
});
