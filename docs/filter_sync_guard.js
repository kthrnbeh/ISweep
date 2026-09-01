/*
 * ISWEEP COMPONENT: Filter-page save guard.
 *
 * Purpose:
 * - Keep the two historical website token keys aligned to the active account.
 * - Verify that pressing Save actually writes selected language words to /preferences.
 * - Retry the SAME backend /preferences save when the legacy page save silently leaves
 *   the backend with an empty blocklist.
 *
 * This does not create a second preference source. The Flask /preferences endpoint
 * remains the durable source of truth; localStorage is only used to build/verify the
 * explicit Save request.
 */
(function () {
  'use strict';

  const SETTINGS_KEY = 'isweep-settings';
  const PREFS_CACHE_KEY = 'isweep-preferences';
  const LEGACY_TOKEN_KEY = 'isweep-token';
  const SHARED_TOKEN_KEY = 'isweep_auth_token';
  const AUTH_STATE_KEY = 'auth-state';
  const BACKEND_URL_KEY = 'isweep-backend-url';
  const DEFAULT_BACKEND = 'http://127.0.0.1:5000';
  const WORDLIST_URL = 'wordlists/language_words.json';
  const LOG = '[ISWEEP][FILTER_SYNC]';

  const CATEGORY_DEFAULTS = {
    language: { action: 'mute', duration: 6, sensitivity: 3 },
    intimacy: { action: 'skip', duration: 15, sensitivity: 3 },
    violence: { action: 'skip', duration: 12, sensitivity: 3 },
    substances: { action: 'log-only', duration: 6, sensitivity: 2 },
    horror: { action: 'fast-forward', duration: 10, sensitivity: 2 },
  };

  let wordLibraryPromise = null;

  function safeJson(raw, fallback = null) {
    try {
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function backendUrl() {
    return String(localStorage.getItem(BACKEND_URL_KEY) || DEFAULT_BACKEND).replace(/\/+$/, '');
  }

  function currentToken() {
    const auth = safeJson(localStorage.getItem(AUTH_STATE_KEY), null);
    return String(
      auth?.token
      || localStorage.getItem(LEGACY_TOKEN_KEY)
      || localStorage.getItem(SHARED_TOKEN_KEY)
      || ''
    ).trim();
  }

  function alignTokenKeys() {
    const token = currentToken();
    if (!token) return null;
    if (localStorage.getItem(LEGACY_TOKEN_KEY) !== token) {
      localStorage.setItem(LEGACY_TOKEN_KEY, token);
    }
    if (localStorage.getItem(SHARED_TOKEN_KEY) !== token) {
      localStorage.setItem(SHARED_TOKEN_KEY, token);
    }
    return token;
  }

  function decodeToken(value) {
    try {
      return atob(String(value || ''));
    } catch (_) {
      return '';
    }
  }

  async function loadWordLibrary() {
    if (wordLibraryPromise) return wordLibraryPromise;
    wordLibraryPromise = fetch(WORDLIST_URL, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`wordlist HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        const language = payload?.language && typeof payload.language === 'object'
          ? payload.language
          : {};
        const result = {};
        Object.entries(language).forEach(([subKey, group]) => {
          const items = Array.isArray(group?.items) ? group.items : [];
          result[subKey] = items.map((item, index) => ({
            id: String(item?.id || `${subKey}-${index}`),
            word: decodeToken(item?.token || '').trim(),
          })).filter((entry) => entry.id && entry.word);
        });
        return result;
      })
      .catch((error) => {
        wordLibraryPromise = null;
        throw error;
      });
    return wordLibraryPromise;
  }

  function mapAction(value, fallback) {
    if (value === 'fast-forward') return 'fast_forward';
    if (value === 'log-only') return 'none';
    if (value === 'skip') return 'skip';
    if (value === 'mute') return 'mute';
    return fallback;
  }

  function mapSensitivity(value) {
    const numeric = Number(value) || 0;
    if (numeric <= 1) return 0.2;
    if (numeric >= 3) return 0.9;
    return 0.7;
  }

  async function buildPreferencesFromSavedSettings() {
    const settings = safeJson(localStorage.getItem(SETTINGS_KEY), null);
    if (!settings || typeof settings !== 'object') {
      throw new Error('No saved Filter settings were found.');
    }

    const library = await loadWordLibrary();
    const selections = settings?.predefined_words?.language || {};
    const selectedWords = [];

    Object.entries(library).forEach(([subKey, items]) => {
      const selectedIds = new Set(
        Array.isArray(selections?.[subKey]?.selectedIds)
          ? selections[subKey].selectedIds.map(String)
          : []
      );
      items.forEach((item) => {
        if (selectedIds.has(item.id)) selectedWords.push(item.word);
      });
    });

    const customWords = Array.isArray(settings?.custom_words?.language)
      ? settings.custom_words.language
          .map((word) => String(word || '').trim())
          .filter(Boolean)
      : [];

    const blocklistItems = Array.from(new Set([
      ...selectedWords,
      ...customWords,
    ]));

    const categories = {};
    Object.entries(CATEGORY_DEFAULTS).forEach(([key, defaults]) => {
      const stored = settings?.actions?.[key] || {};
      const action = mapAction(stored.action, mapAction(defaults.action, 'mute'));
      categories[key] = {
        enabled: settings?.filters_enabled?.[key] !== false,
        action,
        duration: Number(stored.duration) || Number(defaults.duration) || 4,
        sensitivity: mapSensitivity(stored.sensitivity ?? defaults.sensitivity),
      };
    });

    categories.language = {
      ...categories.language,
      items: blocklistItems,
    };

    return {
      enabled: true,
      categories,
      sensitivity: 0.7,
      blocklist: {
        enabled: settings?.filters_enabled?.language !== false,
        mode: 'whole_word',
        action: 'mute',
        duration: Number(settings?.actions?.language?.duration) || 4,
        items: blocklistItems,
      },
    };
  }

  function getWordCount(prefs) {
    if (Array.isArray(prefs?.blocklist?.items)) return prefs.blocklist.items.length;
    if (Array.isArray(prefs?.categories?.language?.items)) return prefs.categories.language.items.length;
    return 0;
  }

  function ensureStatusElement() {
    let status = document.getElementById('isweepFilterSyncStatus');
    if (status) return status;
    const actions = document.querySelector('.filters-actions');
    if (!actions) return null;
    status = document.createElement('div');
    status.id = 'isweepFilterSyncStatus';
    status.setAttribute('role', 'status');
    status.style.marginTop = '8px';
    status.style.fontSize = '0.9rem';
    status.style.width = '100%';
    actions.insertAdjacentElement('afterend', status);
    return status;
  }

  function setStatus(text, isError = false) {
    const status = ensureStatusElement();
    if (!status) return;
    status.textContent = text;
    status.style.color = isError ? '#b42318' : 'var(--muted)';
  }

  async function putPreferences(preferences, token) {
    const response = await fetch(`${backendUrl()}/preferences`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(preferences),
    });

    const bodyText = await response.text();
    let body = {};
    try {
      body = bodyText ? JSON.parse(bodyText) : {};
    } catch (_) {}

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}${bodyText ? `: ${bodyText.slice(0, 160)}` : ''}`);
    }

    localStorage.setItem(PREFS_CACHE_KEY, JSON.stringify(body));
    return body;
  }

  async function verifyOrRepairSave() {
    const token = alignTokenKeys();
    if (!token) {
      setStatus('Saved locally, but not synced: sign in to your ISweep account.', true);
      console.warn(LOG, 'save verification skipped: missing token');
      return;
    }

    let expected;
    try {
      expected = await buildPreferencesFromSavedSettings();
    } catch (error) {
      setStatus(`Could not verify filter save: ${error.message}`, true);
      console.warn(LOG, 'could not build saved preferences', error);
      return;
    }

    const expectedCount = getWordCount(expected);

    await new Promise((resolve) => setTimeout(resolve, 650));

    const cached = safeJson(localStorage.getItem(PREFS_CACHE_KEY), null);
    const cachedCount = getWordCount(cached);

    if (cached && cachedCount === expectedCount) {
      setStatus(`Synced to your ISweep account: ${cachedCount} selected language words.`);
      console.log(LOG, 'normal save verified', { selectedWordCount: cachedCount });
      return;
    }

    console.warn(LOG, 'normal save did not verify; retrying shared /preferences save', {
      expectedCount,
      cachedCount,
    });

    try {
      const saved = await putPreferences(expected, token);
      const savedCount = getWordCount(saved);
      if (savedCount !== expectedCount) {
        throw new Error(`backend returned ${savedCount} words; expected ${expectedCount}`);
      }
      setStatus(`Synced to your ISweep account: ${savedCount} selected language words.`);
      console.log(LOG, 'repair save verified', { selectedWordCount: savedCount });
    } catch (error) {
      setStatus(`Saved locally, but account sync failed: ${error.message}`, true);
      console.error(LOG, 'repair save failed', error);
    }
  }

  alignTokenKeys();

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element
      ? event.target.closest('#saveFilters')
      : null;
    if (!target) return;

    alignTokenKeys();
    setStatus('Saving filters to your ISweep account…');

    setTimeout(() => {
      verifyOrRepairSave().catch((error) => {
        setStatus(`Filter sync check failed: ${error.message}`, true);
        console.error(LOG, 'unexpected save verification error', error);
      });
    }, 0);
  }, true);

  document.addEventListener('click', (event) => {
    const logout = event.target instanceof Element
      ? event.target.closest('[data-logout]')
      : null;
    if (!logout) return;
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    localStorage.removeItem(SHARED_TOKEN_KEY);
  }, true);
})();
