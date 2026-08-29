// Bridges website auth + the last successfully saved backend preferences into extension storage.
//
// Cohesion rule:
//   Filter.html saves to /preferences
//        ↓
//   Backend/database is the durable source of truth
//        ↓
//   Browser clients consume the same saved preference object
//
// This file is intentionally safe to inject more than once. The service worker
// can re-inject it into an already-open ISweep tab after the extension reloads.
(function initIsweepSiteTokenBridge() {
  'use strict';

  if (globalThis.__ISWEEP_SITE_TOKEN_BRIDGE_LOADED__ === true) {
    console.log('[ISWEEP][TOKEN_BRIDGE] already loaded; reusing existing bridge');
    return;
  }
  globalThis.__ISWEEP_SITE_TOKEN_BRIDGE_LOADED__ = true;

  const TOKEN_KEY = 'isweep_auth_token';
  const SITE_PREFS_CACHE_KEY = 'isweep-preferences';
  const EXTENSION_PREFS_KEY = 'isweepPreferences';

  let lastObservedSnapshot = '';

  function safeParseJson(raw, fallback = null) {
    try {
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function normalizeSavedPreferences(raw) {
    const prefs = raw && typeof raw === 'object' ? raw : null;
    if (!prefs) return null;

    const blocklistItems = Array.isArray(prefs?.blocklist?.items)
      ? prefs.blocklist.items
      : Array.isArray(prefs?.categories?.language?.items)
        ? prefs.categories.language.items
        : [];

    const cleanedItems = Array.from(new Set(
      blocklistItems
        .map((word) => typeof word === 'string' ? word.trim().toLowerCase() : '')
        .filter(Boolean)
    ));

    return {
      ...prefs,
      categories: {
        ...(prefs.categories || {}),
        language: {
          ...(prefs.categories?.language || {}),
          items: cleanedItems,
        },
      },
      blocklist: {
        ...(prefs.blocklist || {}),
        items: cleanedItems,
      },
    };
  }

  function readLastSavedBackendPreferences() {
    const cached = safeParseJson(
      window.localStorage.getItem(SITE_PREFS_CACHE_KEY),
      null
    );

    return normalizeSavedPreferences(cached);
  }

  async function copyLastSavedBackendPreferencesToExtension(reason = 'cached_backend_preferences') {
    const prefs = readLastSavedBackendPreferences();

    if (!prefs) {
      console.warn('[ISWEEP][TOKEN_BRIDGE] no saved backend preference cache available', {
        reason,
      });
      return {
        ok: false,
        reason: 'missing_saved_backend_preferences',
        selectedWordCount: 0,
      };
    }

    await chrome.storage.local.set({
      [EXTENSION_PREFS_KEY]: prefs,
    });

    const selectedWordCount = Array.isArray(prefs?.blocklist?.items)
      ? prefs.blocklist.items.length
      : 0;

    console.log('[ISWEEP][TOKEN_BRIDGE] saved backend preferences copied to extension', {
      reason,
      selectedWordCount,
    });

    return {
      ok: true,
      reason,
      selectedWordCount,
    };
  }

  async function refreshExtensionFromSharedPreferences(reason = 'bridge_refresh') {
    try {
      const token = window.localStorage.getItem(TOKEN_KEY);

      if (token) {
        // Copy the website/account token first so the background worker fetches
        // /preferences for the same signed-in account used by the Filters page.
        await chrome.storage.local.set({ [TOKEN_KEY]: token });

        try {
          const syncResult = await chrome.runtime.sendMessage({
            type: 'isweep_sync_prefs',
          });

          if (syncResult?.ok === true || syncResult?.prefs) {
            const store = await chrome.storage.local.get([EXTENSION_PREFS_KEY]);
            const synced = normalizeSavedPreferences(store[EXTENSION_PREFS_KEY]);
            const selectedWordCount = Array.isArray(synced?.blocklist?.items)
              ? synced.blocklist.items.length
              : 0;

            console.log('[ISWEEP][TOKEN_BRIDGE] extension refreshed from shared backend preferences', {
              reason,
              selectedWordCount,
            });

            return {
              ok: true,
              source: 'backend',
              hasToken: true,
              selectedWordCount,
            };
          }
        } catch (error) {
          console.warn('[ISWEEP][TOKEN_BRIDGE] backend preference refresh failed; using last saved cache', {
            reason,
            error: error?.message || error,
          });
        }
      }

      // Resilience only: use the site's cache of the LAST SUCCESSFUL
      // /preferences response. This is saved account state, not unsaved UI state.
      const fallback = await copyLastSavedBackendPreferencesToExtension(reason);

      return {
        ok: fallback.ok,
        source: fallback.ok ? 'last_saved_backend_cache' : 'none',
        hasToken: Boolean(token),
        selectedWordCount: fallback.selectedWordCount || 0,
      };
    } catch (error) {
      console.warn('[ISWEEP][TOKEN_BRIDGE] shared preference bridge failed', {
        reason,
        error: error?.message || error,
      });

      return {
        ok: false,
        source: 'none',
        selectedWordCount: 0,
        error: error?.message || 'bridge_failed',
      };
    }
  }

  function currentSnapshot() {
    return JSON.stringify({
      token: window.localStorage.getItem(TOKEN_KEY) || '',
      // This cache changes only when main.js receives a successful backend
      // preference response.
      savedBackendPreferences:
        window.localStorage.getItem(SITE_PREFS_CACHE_KEY) || '',
    });
  }

  function watchSharedPreferenceChanges() {
    lastObservedSnapshot = currentSnapshot();

    setInterval(() => {
      const nextSnapshot = currentSnapshot();
      if (nextSnapshot === lastObservedSnapshot) return;

      lastObservedSnapshot = nextSnapshot;

      console.log('[ISWEEP][TOKEN_BRIDGE] shared saved preferences changed; refreshing extension');

      refreshExtensionFromSharedPreferences('saved_preferences_changed');
    }, 500);
  }

  // Initial bridge load.
  console.log('[ISWEEP][TOKEN_BRIDGE] loaded on', window.location.href);
  refreshExtensionFromSharedPreferences('page_loaded');
  watchSharedPreferenceChanges();

  // Popup can explicitly request a refresh while an ISweep site tab is active.
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type === 'ISWEEP_PULL_TOKEN') {
      refreshExtensionFromSharedPreferences('popup_requested').then(sendResponse);
      return true;
    }

    return false;
  });
})();
