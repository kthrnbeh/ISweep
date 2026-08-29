// Bridges site-localStorage auth token into extension storage so popup/background share the same Bearer.
const TOKEN_KEY = 'isweep_auth_token'; // Shared token key between site and extension

async function pushTokenToExtension() {
  try {
    const token = window.localStorage.getItem(TOKEN_KEY); // Read token from site localStorage

    if (!token) {
      return { ok: true, hasToken: false }; // No token found but operation is fine
    }

    // Important: wait until the token is actually in extension storage before asking
    // the background worker to fetch /preferences. This removes the old race where
    // preference sync could run before the token write finished.
    await chrome.storage.local.set({ [TOKEN_KEY]: token });

    let syncResult = null;
    try {
      syncResult = await chrome.runtime.sendMessage({ type: 'isweep_sync_prefs' });
    } catch (err) {
      // Background may be restarting. Token is still stored and popup can retry sync.
      console.warn('[ISWEEP][TOKEN_BRIDGE] preference sync request failed', err?.message || err);
    }

    console.log('[ISWEEP][TOKEN_BRIDGE] token copied to extension', {
      prefsSynced: syncResult?.ok === true,
    });

    return {
      ok: true,
      hasToken: true,
      prefsSynced: syncResult?.ok === true,
    };
  } catch (err) {
    console.warn('[ISWEEP][TOKEN_BRIDGE] token bridge failed', err?.message || err);
    return { ok: false, error: err?.message || 'token read failed' };
  }
}

// Push once on load. GitHub Pages and local development pages both use this bridge.
pushTokenToExtension();

// Respond to explicit pulls from popup/background.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'ISWEEP_PULL_TOKEN') {
    pushTokenToExtension().then(sendResponse);
    return true; // Keep the message channel open for the async response.
  }
  return false;
});
