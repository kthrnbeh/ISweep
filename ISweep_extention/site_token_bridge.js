// Requests a background-owned credential sync. The page may read its own
// localStorage, but it never writes extension storage or decides whether two
// accounts are compatible; the service worker validates the bearer token.
const TOKEN_KEY = 'isweep_auth_token';
const PREFS_CACHE_KEY = 'isweep-preferences'; // Updated after a successful backend save.
const USER_ID_KEY = 'isweep-user-id';

async function pushTokenToExtension() {
  try {
    const token = window.localStorage.getItem(TOKEN_KEY);

    if (!token) {
      return { ok: true, hasToken: false };
    }

    let syncResult = null;
    try {
      syncResult = await chrome.runtime.sendMessage({
        type: 'isweep_sync_prefs',
        token,
        userId: window.localStorage.getItem(USER_ID_KEY) || null,
      });
    } catch (err) {
      console.warn('[ISWEEP][TOKEN_BRIDGE] preference sync request failed', err?.message || err);
    }

    console.log('[ISWEEP][TOKEN_BRIDGE] token copied to extension', {
      prefsSynced: syncResult?.ok === true,
    });

    return {
      ok: syncResult?.ok === true,
      hasToken: true,
      prefsSynced: syncResult?.ok === true,
      error: syncResult?.ok === true ? null : (syncResult?.error || 'preference sync failed'),
    };
  } catch (err) {
    console.warn('[ISWEEP][TOKEN_BRIDGE] token bridge failed', err?.message || err);
    return { ok: false, error: err?.message || 'token read failed' };
  }
}

function watchHostedPreferenceChanges() {
  let lastSnapshot = window.localStorage.getItem(PREFS_CACHE_KEY) || '';

  setInterval(() => {
    const nextSnapshot = window.localStorage.getItem(PREFS_CACHE_KEY) || '';
    if (nextSnapshot === lastSnapshot) return;

    lastSnapshot = nextSnapshot;
    console.log('[ISWEEP][TOKEN_BRIDGE] site preferences changed; syncing extension');
    pushTokenToExtension();
  }, 800);
}

// Push once on load, then keep the extension preference cache aligned with
// successful saves made on the hosted Filters page.
pushTokenToExtension();
watchHostedPreferenceChanges();

// Respond to explicit pulls from popup/background.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'ISWEEP_PULL_TOKEN') {
    pushTokenToExtension().then(sendResponse);
    return true; // Keep the message channel open for the async response.
  }
  return false;
});
