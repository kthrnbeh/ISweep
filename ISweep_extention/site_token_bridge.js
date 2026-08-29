// Bridges hosted/local website auth + saved Filter selections into extension storage.
// This keeps the extension's cached preferences aligned with the Filter page even
// when a backend refresh is delayed or temporarily unavailable.
const TOKEN_KEY = 'isweep_auth_token';
const SITE_PREFS_CACHE_KEY = 'isweep-preferences';
const SITE_SETTINGS_KEY = 'isweep-settings';
const EXTENSION_PREFS_KEY = 'isweepPreferences';
const LANGUAGE_WORDLIST_PATH = 'wordlists/language_words.json';

let cachedWordLibrary = null;
let lastObservedSnapshot = '';

function safeParseJson(raw, fallback = null) {
  try {
    return raw ? JSON.parse(raw) : fallback;
  } catch (_) {
    return fallback;
  }
}

function decodeToken(token) {
  try {
    return atob(String(token || ''));
  } catch (_) {
    return '';
  }
}

async function loadLanguageWordLibrary() {
  if (cachedWordLibrary) return cachedWordLibrary;

  try {
    const url = new URL(LANGUAGE_WORDLIST_PATH, window.location.href);
    const response = await fetch(url.toString(), { cache: 'no-store' });
    if (!response.ok) throw new Error(`status ${response.status}`);

    const data = await response.json();
    const language = data?.language && typeof data.language === 'object'
      ? data.language
      : {};
    const mapped = {};

    Object.entries(language).forEach(([subKey, payload]) => {
      const items = Array.isArray(payload?.items) ? payload.items : [];
      mapped[subKey] = items.map((item, index) => ({
        id: String(item?.id || `${subKey}-${index}`),
        word: decodeToken(item?.token || ''),
      })).filter((entry) => entry.id && entry.word);
    });

    cachedWordLibrary = mapped;
    return cachedWordLibrary;
  } catch (error) {
    console.warn('[ISWEEP][TOKEN_BRIDGE] word library load failed', error?.message || error);
    return null;
  }
}

async function buildPreferencesFromFilterSettings() {
  const settings = safeParseJson(window.localStorage.getItem(SITE_SETTINGS_KEY), null);
  if (!settings || typeof settings !== 'object') return null;

  const library = await loadLanguageWordLibrary();
  if (!library) return null;

  const selectedWords = [];
  const selections = settings?.predefined_words?.language || {};

  Object.entries(library).forEach(([subKey, items]) => {
    const selectedIds = new Set(
      Array.isArray(selections?.[subKey]?.selectedIds)
        ? selections[subKey].selectedIds.map(String)
        : []
    );

    items.forEach((item) => {
      if (selectedIds.has(String(item.id)) && item.word) {
        selectedWords.push(item.word.trim().toLowerCase());
      }
    });
  });

  const customWords = Array.isArray(settings?.custom_words?.language)
    ? settings.custom_words.language
        .map((word) => String(word || '').trim().toLowerCase())
        .filter(Boolean)
    : [];

  const blocklistItems = Array.from(new Set([
    ...selectedWords,
    ...customWords,
  ])).filter(Boolean);

  const cachedPrefs = safeParseJson(
    window.localStorage.getItem(SITE_PREFS_CACHE_KEY),
    {}
  ) || {};

  const languageEnabled = settings?.filters_enabled?.language !== false;
  const languageDuration = Number(settings?.actions?.language?.duration) || 4;

  return {
    ...cachedPrefs,
    enabled: cachedPrefs.enabled !== false,
    categories: {
      ...(cachedPrefs.categories || {}),
      language: {
        ...(cachedPrefs.categories?.language || {}),
        enabled: languageEnabled,
        action: 'mute',
        duration: languageDuration,
        items: blocklistItems,
      },
    },
    blocklist: {
      ...(cachedPrefs.blocklist || {}),
      enabled: languageEnabled,
      mode: 'whole_word',
      action: 'mute',
      duration: languageDuration,
      items: blocklistItems,
    },
  };
}

async function copySitePreferencesToExtension() {
  const prefs = await buildPreferencesFromFilterSettings();
  if (!prefs) {
    console.warn('[ISWEEP][TOKEN_BRIDGE] no Filter settings available to mirror');
    return { ok: false, reason: 'missing_filter_settings' };
  }

  await chrome.storage.local.set({
    [EXTENSION_PREFS_KEY]: prefs,
  });

  const count = Array.isArray(prefs?.blocklist?.items)
    ? prefs.blocklist.items.length
    : 0;

  console.log('[ISWEEP][TOKEN_BRIDGE] Filter selections copied to extension', {
    selectedWordCount: count,
  });

  return {
    ok: true,
    selectedWordCount: count,
  };
}

async function pushSiteStateToExtension() {
  try {
    const token = window.localStorage.getItem(TOKEN_KEY);

    if (token) {
      // Store the website token first so the background worker can still use the
      // normal /preferences endpoint as the durable account source of truth.
      await chrome.storage.local.set({ [TOKEN_KEY]: token });

      try {
        await chrome.runtime.sendMessage({ type: 'isweep_sync_prefs' });
      } catch (error) {
        console.warn('[ISWEEP][TOKEN_BRIDGE] backend preference refresh failed', error?.message || error);
      }
    }

    // Always mirror the Filter page's current saved selections after the backend
    // refresh attempt. This removes the old 0/[missing] gap in the extension.
    const localMirror = await copySitePreferencesToExtension();

    return {
      ok: localMirror.ok,
      hasToken: Boolean(token),
      selectedWordCount: localMirror.selectedWordCount || 0,
    };
  } catch (error) {
    console.warn('[ISWEEP][TOKEN_BRIDGE] site state bridge failed', error?.message || error);
    return { ok: false, error: error?.message || 'bridge_failed' };
  }
}

function currentSnapshot() {
  return JSON.stringify({
    token: window.localStorage.getItem(TOKEN_KEY) || '',
    prefs: window.localStorage.getItem(SITE_PREFS_CACHE_KEY) || '',
    settings: window.localStorage.getItem(SITE_SETTINGS_KEY) || '',
  });
}

function watchHostedPreferenceChanges() {
  lastObservedSnapshot = currentSnapshot();

  setInterval(() => {
    const nextSnapshot = currentSnapshot();
    if (nextSnapshot === lastObservedSnapshot) return;

    lastObservedSnapshot = nextSnapshot;
    console.log('[ISWEEP][TOKEN_BRIDGE] website settings changed; refreshing extension cache');
    pushSiteStateToExtension();
  }, 500);
}

// Push once on load, then keep extension storage aligned with Filter saves.
pushSiteStateToExtension();
watchHostedPreferenceChanges();

// Popup can explicitly request a refresh while the Filter page is active.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'ISWEEP_PULL_TOKEN') {
    pushSiteStateToExtension().then(sendResponse);
    return true;
  }
  return false;
});
