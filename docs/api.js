// Lightweight API helper for the Settings page. No frameworks, Live Server friendly.
// Provides: healthCheck, getPreferences, putPreferences. Uses BACKEND_URL configurable via localStorage.

const BACKEND_URL_KEY = 'isweep-backend-url';
const BACKEND_URL = localStorage.getItem(BACKEND_URL_KEY) || 'http://127.0.0.1:8000';

/**
 * Check backend availability with a fast GET /health.
 * Returns true on success, false on network error.
 */
async function healthCheck() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { method: 'GET' });
    return res.ok;
  } catch (err) {
    console.warn('[ISweep API] Health check failed', err);
    return false;
  }
}

/**
 * Fetch user preferences from the backend.
 * Accepts a userId string; Authorization uses token==userId for prototype mode.
 */
async function getPreferences(userId) {
  const res = await fetch(`${BACKEND_URL}/preferences?user_id=${encodeURIComponent(userId)}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${userId}` }
  });
  if (!res.ok) {
    throw new Error(`Failed to get preferences (${res.status})`);
  }
  const json = await res.json();
  return json.preferences || {};
}

/**
 * Persist user preferences to the backend.
 * Accepts a userId string and a preferences object; returns the saved prefs.
 */
async function putPreferences(userId, prefs) {
  const res = await fetch(`${BACKEND_URL}/preferences`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${userId}`
    },
    body: JSON.stringify({ user_id: userId, ...prefs })
  });
  if (!res.ok) {
    throw new Error(`Failed to save preferences (${res.status})`);
  }
  const json = await res.json();
  return json.preferences || prefs;
}

// Expose for other scripts loaded after this file.
window.ISweepApi = { BACKEND_URL, BACKEND_URL_KEY, healthCheck, getPreferences, putPreferences };
