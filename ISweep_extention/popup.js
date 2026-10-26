// ISweep Chrome Extension - Popup Controller
// Handles UI state, authentication flow, and user interactions
// IMPORTANT:
// chrome.runtime.sendMessage only works inside the extension context.
// Do NOT test runtime messaging from normal webpage DevTools. Use the extension service worker console instead.

// Configuration - Web App Base URL
// Default to public GitHub Pages; allow override via stored setting for local dev.
const DEFAULT_FRONTEND_BASE = 'https://kthrnbeh.github.io/ISweep';
const DEFAULT_BACKEND = 'http://127.0.0.1:5000';
const DEFAULT_LOCAL_FRONTEND_BASE = 'http://127.0.0.1:5500/ISweep_frontend/docs';

// Storage Keys
const STORAGE_KEYS = {
  AUTH: 'isweepAuth',              // Cached auth info
  ENABLED: 'isweepEnabled',        // Toggle for filtering
  TOKEN: 'isweep_auth_token',      // Unified token key
  USER_ID: 'isweepUserId',         // Legacy user id key
  PREFS: 'isweepPreferences',      // Cached preferences
  LEARNING_CONSENT_CONFIRMED: 'isweepLearningConsentConfirmed',
  BACKEND_URL: 'isweepBackendUrl', // Backend base URL
  FRONTEND_URL: 'isweepFrontendUrl',// Frontend base URL override
  CLEAN_CAPTION_SETTINGS: 'isweepCleanCaptionSettings',
  DEV_LOCAL_AUTH: 'devLocalAuthEnabled',
};

const CLEAN_CAPTION_DEFAULTS = {
  cleanCaptionsEnabled: true,
  cleanCaptionStyle: 'transparent_white',
  cleanCaptionTextSize: 'medium',
  cleanCaptionWordMuteMode: 'captions_only',
  cleanCaptionPosition: { x: 0.5, y: 0.8 },
};

function normalizeCleanCaptionSettings(raw) {
  const data = raw && typeof raw === 'object' ? raw : {};
  const style = data.cleanCaptionStyle === 'white_black' ? 'white_black' : 'transparent_white';
  const textSize = ['small', 'medium', 'large'].includes(data.cleanCaptionTextSize)
    ? data.cleanCaptionTextSize
    : 'medium';
  const wordMuteMode = (data.cleanCaptionWordMuteMode === 'captions_word_mute'
    || data.cleanCaptionWordMuteMode === 'captions_selected_word_mute')
    ? 'captions_word_mute'
    : 'captions_only';
  const enabled = data.cleanCaptionsEnabled !== false;
  const position = data.cleanCaptionPosition
    && Number.isFinite(Number(data.cleanCaptionPosition.x))
    && Number.isFinite(Number(data.cleanCaptionPosition.y))
    ? {
      x: Math.max(0, Math.min(1, Number(data.cleanCaptionPosition.x))),
      y: Math.max(0, Math.min(1, Number(data.cleanCaptionPosition.y))),
    }
    : { ...CLEAN_CAPTION_DEFAULTS.cleanCaptionPosition };
  return {
    cleanCaptionsEnabled: enabled,
    cleanCaptionStyle: style,
    cleanCaptionTextSize: textSize,
    cleanCaptionWordMuteMode: wordMuteMode,
    cleanCaptionPosition: position,
  };
}

// Shared token key used by the site and the bridge content script.
const TOKEN_KEY = 'isweep_auth_token';

const LOG_PREFIX = '[ISWEEP][POPUP]'; // Standard log prefix

function isLocalBackendUrl(url) {
  const value = String(url || '').trim().toLowerCase();
  return value.startsWith('http://127.0.0.1') || value.startsWith('http://localhost');
}

async function getBackendUrl() {
  const store = await chrome.storage.local.get([STORAGE_KEYS.BACKEND_URL]); // Fetch stored backend URL
  const value = String(store[STORAGE_KEYS.BACKEND_URL] || '').trim();
  let normalized = DEFAULT_BACKEND;
  if (value) {
    try {
      const parsed = new URL(value);
      const port = parsed.port || '80';
      if (parsed.protocol === 'http:' && parsed.hostname === '127.0.0.1' && port === '5000') {
        normalized = DEFAULT_BACKEND;
      }
    } catch (_) {
      normalized = DEFAULT_BACKEND;
    }
  }
  if (store[STORAGE_KEYS.BACKEND_URL] !== normalized) {
    await chrome.storage.local.set({ [STORAGE_KEYS.BACKEND_URL]: normalized });
  }
  return normalized;
}

async function getFrontendBaseUrl() {
  const store = await chrome.storage.local.get([STORAGE_KEYS.FRONTEND_URL]); // Fetch stored frontend URL
  const base = store[STORAGE_KEYS.FRONTEND_URL] || DEFAULT_FRONTEND_BASE; // Default to hosted frontend
  return base.replace(/\/+$/, ''); // Trim trailing slashes
}

async function getPreferredFrontendBaseUrl() {
  const store = await chrome.storage.local.get([STORAGE_KEYS.FRONTEND_URL, STORAGE_KEYS.BACKEND_URL]);
  const configuredFrontend = String(store[STORAGE_KEYS.FRONTEND_URL] || '').trim();
  if (configuredFrontend) return configuredFrontend.replace(/\/+$/, '');

  const backend = String(store[STORAGE_KEYS.BACKEND_URL] || DEFAULT_BACKEND).trim();
  if (isLocalBackendUrl(backend)) return DEFAULT_LOCAL_FRONTEND_BASE;
  return DEFAULT_FRONTEND_BASE;
}

async function saveAuthSession({ authData }) {
  const payload = {
    [STORAGE_KEYS.AUTH]: authData,   // Persist auth payload
    [STORAGE_KEYS.ENABLED]: true,    // Enable filtering by default after login
  };
  await chrome.storage.local.set(payload); // Save to storage
}

// DOM Elements - Logged Out State
const stateLoggedOut = document.getElementById('stateLoggedOut'); // Logged-out container
const btnLogin = document.getElementById('btnLogin'); // Login button
const linkCreateAccount = document.getElementById('linkCreateAccount'); // Create account link
const quickLoginForm = document.getElementById('quickLoginForm'); // Inline login form
const emailInput = document.getElementById('emailInput'); // Email input field
const passwordInput = document.getElementById('passwordInput'); // Password input field
const btnQuickLogin = document.getElementById('btnQuickLogin'); // Submit quick login
const btnCreateLocalDevAccount = document.getElementById('btnCreateLocalDevAccount');
const btnCancelQuickLogin = document.getElementById('btnCancelQuickLogin'); // Cancel quick login

// DOM Elements - Logged In State
const stateLoggedIn = document.getElementById('stateLoggedIn'); // Logged-in container
const userAvatar = document.getElementById('userAvatar'); // Avatar element (not dynamically used yet)
const userInitials = document.getElementById('userInitials'); // Initials badge
const userName = document.getElementById('userName'); // Display name text
const statusDot = document.getElementById('statusDot'); // Status indicator dot
const statusText = document.getElementById('statusText'); // Status text label
const btnOpenSettings = document.getElementById('btnOpenSettings'); // Open filters/settings
const btnSyncPrefs = document.getElementById('btnSyncPrefs'); // Sync prefs button
const linkResetFilters = document.getElementById('linkResetFilters'); // Reset filters link
const linkManageAccount = document.getElementById('linkManageAccount'); // Manage account link
const linkLogout = document.getElementById('linkLogout'); // Logout link
const signedInStatus = document.getElementById('signedInStatus'); // Status line about prefs cache
const btnCleanCaptionsToggle = document.getElementById('btnCleanCaptionsToggle');
const btnCaptionAppearance = document.getElementById('btnCaptionAppearance');
const captionSettingsPanel = document.getElementById('captionSettingsPanel');
const captionRuntimeStatus = document.getElementById('captionRuntimeStatus');
const backendStateValue = document.getElementById('backendStateValue');
const backendUrlValue = document.getElementById('backendUrlValue');
const backendLastErrorValue = document.getElementById('backendLastErrorValue');
const backendSttStatusValue = document.getElementById('backendSttStatusValue');
const backendLastSuccessCaptionValue = document.getElementById('backendLastSuccessCaptionValue');
const captionStateValue = document.getElementById('captionStateValue');
const primaryCaptionSourceValue = document.getElementById('primaryCaptionSourceValue');
const currentChunkIdValue = document.getElementById('currentChunkIdValue');
const lastAcceptedWindowValue = document.getElementById('lastAcceptedWindowValue');
const lastDropReasonValue = document.getElementById('lastDropReasonValue');
const pageTextAssistSourceValue = document.getElementById('pageTextAssistSourceValue');
const sttPageAgreementValue = document.getElementById('sttPageAgreementValue');
const captionModeValue = document.getElementById('captionModeValue');
const selectedWordsCountValue = document.getElementById('selectedWordsCountValue');
const selectedWordsPreviewValue = document.getElementById('selectedWordsPreviewValue');
const cleanCaptionStyleSelect = document.getElementById('cleanCaptionStyle');
const cleanCaptionTextSizeSelect = document.getElementById('cleanCaptionTextSize');
const cleanCaptionWordMuteModeSelect = document.getElementById('cleanCaptionWordMuteMode');
const btnResetCaptionPosition = document.getElementById('btnResetCaptionPosition');
const learningConsentToggle = document.getElementById('learningConsentToggle');
const learningConsentStatus = document.getElementById('learningConsentStatus');
const learningEventsPanel = document.getElementById('learningEventsPanel');
const learningEventsList = document.getElementById('learningEventsList');
const btnReportMissedWord = document.getElementById('btnReportMissedWord');
const learningMissedVideoId = document.getElementById('learningMissedVideoId');
const learningMissedWord = document.getElementById('learningMissedWord');
const learningMissedStart = document.getElementById('learningMissedStart');
const learningMissedEnd = document.getElementById('learningMissedEnd');
const btnLearningMissedStartNow = document.getElementById('btnLearningMissedStartNow');
const btnLearningMissedEndNow = document.getElementById('btnLearningMissedEndNow');

let cleanCaptionSettingsCache = { ...CLEAN_CAPTION_DEFAULTS };

function parsePlaybackTime(value) {
  const text = String(value ?? '').trim();
  if (!text) return null;
  if (!text.includes(':')) {
    const seconds = Number(text);
    return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
  }
  const parts = text.split(':');
  if (parts.length === 2) {
    const minutes = Number(parts[0]);
    const seconds = Number(parts[1]);
    if (!Number.isInteger(minutes) || minutes < 0 || !Number.isFinite(seconds) || seconds < 0 || seconds >= 60) return null;
    return minutes * 60 + seconds;
  }
  if (parts.length === 3) {
    const hours = Number(parts[0]);
    const minutes = Number(parts[1]);
    const seconds = Number(parts[2]);
    if (!Number.isInteger(hours) || hours < 0 || !Number.isInteger(minutes) || minutes < 0 || minutes >= 60
      || !Number.isFinite(seconds) || seconds < 0 || seconds >= 60) return null;
    return hours * 3600 + minutes * 60 + seconds;
  }
  return null;
}

function formatPlaybackTime(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return '--:--';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = (seconds % 60).toFixed(2).padStart(5, '0');
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${remainder}`;
  return `${minutes}:${remainder}`;
}

function eventOccurrenceKey(event) {
  const start = Number(event?.predicted_start_seconds);
  const end = Number(event?.predicted_end_seconds);
  const rounded = (value) => Number.isFinite(value) ? (Math.round(value * 2) / 2).toFixed(1) : 'unknown';
  return `${String(event?.video_id || '')}|${String(event?.matched_word || '').trim().toLowerCase()}|${rounded(start)}|${rounded(end)}`;
}

function groupLearningEvents(events) {
  const groups = new Map();
  (Array.isArray(events) ? events : [])
    .slice()
    .sort((left, right) => Number(right.event_id || 0) - Number(left.event_id || 0))
    .forEach((event) => {
      const key = eventOccurrenceKey(event);
      const group = groups.get(key) || { key, representative: event, attempts: [] };
      group.attempts.push(event);
      if (event.feedback && !group.representative.feedback) group.representative = event;
      groups.set(key, group);
    });
  return Array.from(groups.values());
}

async function getActiveVideoClock() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return null;
    const clock = await chrome.tabs.sendMessage(tab.id, { type: 'isweep_get_video_clock' });
    return clock?.ok && Number.isFinite(Number(clock.current_time)) ? clock : null;
  } catch (_) {
    return null;
  }
}

async function captureCurrentVideoTime(input) {
  const clock = await getActiveVideoClock();
  if (!clock) {
    if (learningConsentStatus) learningConsentStatus.textContent = 'Open an active YouTube video to capture its current time.';
    return false;
  }
  if (input) input.value = formatPlaybackTime(clock.current_time);
  if (learningMissedVideoId && clock.video_id && !learningMissedVideoId.value.trim()) {
    learningMissedVideoId.value = clock.video_id;
  }
  return true;
}

function setSyncPrefsAvailability(hasToken) {
  if (!btnSyncPrefs) return;
  const enabled = hasToken === true;
  btnSyncPrefs.disabled = !enabled;
  btnSyncPrefs.setAttribute('aria-disabled', enabled ? 'false' : 'true');
  btnSyncPrefs.title = enabled
    ? 'Sync preferences from your ISweep account'
    : 'Sign in on the ISweep site to sync preferences';
}

function renderCaptionRuntimeStatus(status) {
  if (!captionRuntimeStatus) return;
  const state = typeof status?.state === 'string' ? status.state : 'backend_offline';
  const label = typeof status?.label === 'string' ? status.label : 'Audio captions: Backend offline';
  const sourceLabel = typeof status?.sourceLabel === 'string' ? status.sourceLabel : '';
  captionRuntimeStatus.textContent = sourceLabel ? `Caption source: ${sourceLabel}` : label;
  captionRuntimeStatus.dataset.state = state;
}

function toRelativeTimeLabel(epochMs) {
  const value = Number(epochMs);
  if (!Number.isFinite(value) || value <= 0) return 'never';
  const deltaSec = Math.max(Math.floor((Date.now() - value) / 1000), 0);
  if (deltaSec < 1) return 'just now';
  if (deltaSec < 60) return `${deltaSec}s ago`;
  const min = Math.floor(deltaSec / 60);
  if (min < 60) return `${min}m ago`;
  const hrs = Math.floor(min / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function renderCaptionReadiness(status) {
  const readiness = status?.readiness && typeof status.readiness === 'object' ? status.readiness : status;
  const backend = readiness?.backend && typeof readiness.backend === 'object' ? readiness.backend : {};

  if (backendStateValue) {
    const backendState = String(backend.state || '').trim().toLowerCase();
    if (backendState === 'ready') {
      backendStateValue.textContent = 'Ready';
    } else if (backendState === 'stt_disabled') {
      backendStateValue.textContent = 'STT Disabled';
    } else {
      backendStateValue.textContent = 'Offline';
    }
  }
  if (backendUrlValue) {
    backendUrlValue.textContent = String(backend.backendUrl || DEFAULT_BACKEND);
  }
  if (backendLastErrorValue) {
    const reasonCode = String(backend.reasonCode || status?.reasonCode || readiness?.lastFailureReason || '').trim();
    const detail = String(backend.errorMessage || readiness?.lastError || '').trim();
    backendLastErrorValue.textContent = reasonCode || detail ? `${reasonCode || 'error'}${detail ? ` (${detail})` : ''}` : 'none';
  }
  if (backendSttStatusValue) {
    const sttStatus = String(readiness?.sttStatus || backend.sttStatus || 'unknown');
    const sttError = String(readiness?.sttError || '').trim();
    backendSttStatusValue.textContent = sttError ? `${sttStatus} (${sttError})` : sttStatus;
  }
  if (backendLastSuccessCaptionValue) {
    const since = toRelativeTimeLabel(readiness?.lastSuccessfulCaptionAt);
    const latency = Number.isFinite(Number(readiness?.lastCaptionLatencyMs))
      ? `, ${Math.round(Number(readiness.lastCaptionLatencyMs))}ms`
      : '';
    backendLastSuccessCaptionValue.textContent = `${since}${latency}`;
  }
  if (captionStateValue) {
    captionStateValue.textContent = String(status?.captionState || readiness?.captionState || 'Listening');
  }
  if (primaryCaptionSourceValue) {
    primaryCaptionSourceValue.textContent = String(
      readiness?.primaryCaptionSource
      || status?.primaryCaptionSource
      || 'Waiting for audio'
    );
  }
  if (currentChunkIdValue) {
    currentChunkIdValue.textContent = String(status?.currentChunkId || readiness?.currentChunkId || 'none');
  }
  if (lastAcceptedWindowValue) {
    const endMs = Number(status?.lastAcceptedWindowEndMs ?? readiness?.lastAcceptedWindowEndMs);
    lastAcceptedWindowValue.textContent = Number.isFinite(endMs) && endMs >= 0 ? `${endMs}ms` : 'none';
  }
  if (lastDropReasonValue) {
    lastDropReasonValue.textContent = String(status?.lastDroppedReason || readiness?.lastDroppedReason || 'none');
  }
  if (pageTextAssistSourceValue) {
    const source = String(status?.pageTextAssistSource || readiness?.pageTextAssistSource || 'none');
    const assistState = String(status?.pageTextAssistState || readiness?.pageTextAssistState || '').trim();
    pageTextAssistSourceValue.textContent = assistState ? `${source} (${assistState})` : source;
  }
  if (sttPageAgreementValue) {
    sttPageAgreementValue.textContent = String(status?.sttPageAgreement || readiness?.sttPageAgreement || 'unavailable');
  }
  if (captionModeValue) {
    captionModeValue.textContent = String(readiness?.captionModeLabel || 'Captions Only');
  }
  if (selectedWordsCountValue) {
    selectedWordsCountValue.textContent = String(Number(readiness?.selectedWordCount || 0));
  }
  if (selectedWordsPreviewValue) {
    const preview = Array.isArray(readiness?.selectedWordPreview) ? readiness.selectedWordPreview : [];
    const source = String(readiness?.selectedWordSource || '').trim();
    const sourceSuffix = source ? ` [${source}]` : '';
    selectedWordsPreviewValue.textContent = preview.length
      ? `${preview.slice(0, 8).join(', ')}${sourceSuffix}`
      : `(none)${sourceSuffix}`;
  }
}

async function refreshCaptionRuntimeStatus() {
  try {
    const status = await chrome.runtime.sendMessage({ type: 'isweep_get_caption_runtime_status' });
    renderCaptionRuntimeStatus(status);
    renderCaptionReadiness(status);
    const backendOk = status?.backend?.ok === true || status?.backendOnline === true;
    const sttEnabled = status?.backend?.stt_enabled === true || status?.sttEnabled === true;
    const captionSource = String(status?.source || status?.sourceLabel || status?.state || 'unknown');
    console.log('[ISWEEP][POPUP] health status', {
      backendOk,
      stt_enabled: sttEnabled,
      captionSource,
    });
    console.log('[ISWEEP][CAPTIONS]', 'popup status refreshed', status);
  } catch (error) {
    renderCaptionRuntimeStatus({ state: 'backend_offline', label: 'Audio captions: Backend offline' });
    renderCaptionReadiness({
      backend: {
        ready: false,
        backendUrl: DEFAULT_BACKEND,
        reasonCode: 'backend_unreachable',
      },
      sttStatus: 'unknown',
    });
    console.log('[ISWEEP][CAPTIONS]', 'popup status refresh failed', error?.message || error);
  }
}

/**
 * Initialize popup on load
 * Loads auth and enabled state from chrome.storage.local
 * Renders the appropriate UI state
 */
document.addEventListener('DOMContentLoaded', async () => {
  console.log(LOG_PREFIX, 'initializing...');
  
  try {
    // Load stored data from chrome.storage.local
    const result = await chrome.storage.local.get([
      STORAGE_KEYS.AUTH,
      STORAGE_KEYS.ENABLED,
      TOKEN_KEY,
      STORAGE_KEYS.USER_ID,
      STORAGE_KEYS.PREFS,
      STORAGE_KEYS.LEARNING_CONSENT_CONFIRMED,
      STORAGE_KEYS.DEV_LOCAL_AUTH,
      STORAGE_KEYS.BACKEND_URL,
    ]);
    
    let authData = result[STORAGE_KEYS.AUTH]; // Pull cached auth data
    const hasToken = Boolean(result[TOKEN_KEY]); // Token presence
    const isEnabled = result[STORAGE_KEYS.ENABLED] !== false; // Default to true if not set
    const devLocalAuthActive = result[STORAGE_KEYS.DEV_LOCAL_AUTH] === true
      && isLocalBackendUrl(result[STORAGE_KEYS.BACKEND_URL] || 'http://127.0.0.1:5000');
    
    console.log(LOG_PREFIX, 'Auth data:', authData ? 'Present' : 'None', 'token:', hasToken);
    console.log(LOG_PREFIX, 'Enabled state:', isEnabled);

    // Fallback: if token exists but authData missing, synthesize minimal auth so UI shows logged-in
    if (!authData && hasToken) {
      authData = { email: '(signed in)', displayName: 'ISweep user', initials: '--', loggedInAt: new Date().toISOString() };
    }

    if (!authData && !hasToken && devLocalAuthActive) {
      console.log('[ISWEEP][AUTH] dev local auth enabled');
      console.log('[ISWEEP][AUTH] using local preferences fallback');
      authData = {
        email: '(dev-local)',
        displayName: 'ISweep local dev',
        initials: 'DL',
        loggedInAt: new Date().toISOString(),
      };
    }
    
    if (authData && (authData.email || hasToken)) {
      renderLoggedInState(authData, isEnabled); // Show logged-in UI
      setSyncPrefsAvailability(hasToken);
      // Reflect cached prefs status for clarity.
      if (signedInStatus) {
        const prefs = result[STORAGE_KEYS.PREFS];
        if (devLocalAuthActive && !hasToken) {
          signedInStatus.textContent = prefs
            ? 'Dev local auth enabled. Using cached preferences.'
            : 'Dev local auth enabled. No cached preferences yet.';
        } else {
          signedInStatus.textContent = prefs ? 'Signed in. Preferences cached.' : 'Signed in. No preferences cached yet.';
        }
      }
      const learningEnabled = result[STORAGE_KEYS.LEARNING_CONSENT_CONFIRMED] === true
        && result[STORAGE_KEYS.PREFS]?.learning?.enabled === true;
      setLearningConsentUi(learningEnabled);
      if (learningEnabled) await refreshLearningEvents();
    } else {
      renderLoggedOutState(); // Show logged-out UI
      setSyncPrefsAvailability(false);
    }
    
    // Set up event listeners
    setupEventListeners();
    const activeClock = await getActiveVideoClock();
    if (activeClock?.video_id && learningMissedVideoId && !learningMissedVideoId.value.trim()) {
      learningMissedVideoId.value = activeClock.video_id;
    }
    await initCleanCaptionControls();
    await refreshCaptionRuntimeStatus();
    
  } catch (error) {
    console.error(LOG_PREFIX, 'Error initializing:', error);
    renderLoggedOutState(); // Fallback to logged out state
  }
});

/**
 * Render the Logged Out state
 */
function renderLoggedOutState() {
  console.log(LOG_PREFIX, 'rendering logged out state');
  stateLoggedOut.classList.remove('hidden'); // Show logged-out view
  stateLoggedIn.classList.add('hidden'); // Hide logged-in view
  if (learningEventsPanel) learningEventsPanel.classList.add('hidden');
  if (learningConsentToggle) learningConsentToggle.checked = false;
  if (learningConsentStatus) learningConsentStatus.textContent = 'Off. No learning events are uploaded.';
}

/**
 * Render the Logged In state
 * @param {Object} authData - User authentication data {email, displayName, initials, loggedInAt}
 * @param {boolean} isEnabled - Whether ISweep filtering is enabled
 */
function renderLoggedInState(authData, isEnabled) {
  console.log(LOG_PREFIX, 'rendering logged in state');
  
  // Update user display name
  const displayName = authData.displayName || authData.email.split('@')[0]; // Prefer displayName else email prefix
  userName.textContent = displayName;
  
  // Update avatar initials
  userInitials.textContent = 'KA'; // Static placeholder initials
  
  // Update status based on enabled state
  if (isEnabled) {
    statusDot.classList.remove('paused');
    statusText.textContent = 'ISweep is Active';
  } else {
    statusDot.classList.add('paused');
    statusText.textContent = 'ISweep is Paused';
  }
  if (signedInStatus) signedInStatus.textContent = 'Signed in.'; // Basic signed-in indicator
  
  // Show logged in state, hide logged out state
  stateLoggedIn.classList.remove('hidden');
  stateLoggedOut.classList.add('hidden');
}

function setLearningConsentUi(enabled, message = null) {
  const active = enabled === true;
  if (learningConsentToggle) learningConsentToggle.checked = active;
  if (learningConsentStatus) {
    learningConsentStatus.textContent = message
      || (active ? 'On. Timing events may be uploaded after backend confirmation.' : 'Off. No learning events are uploaded.');
  }
  if (learningEventsPanel) learningEventsPanel.classList.toggle('hidden', !active);
}

function syncCorrectionFieldVisibility(result, start, end) {
  const useful = ['early', 'late', 'missed'].includes(result) || Boolean(start?.value || end?.value);
  if (start) start.hidden = !useful;
  if (end) end.hidden = !useful;
}

function hasSavedFeedback(event) {
  return Boolean(event?.feedback && typeof event.feedback.result === 'string' && event.feedback.result);
}

function learningFeedbackErrorMessage(response, action = 'save') {
  const verb = action === 'remove' ? 'remove the saved correction' : 'save the correction';
  if (response?.error === 'unauthorized' || response?.status === 401) {
    return `Could not ${verb}: your session expired. Sign in again and retry.`;
  }
  if (response?.error === 'backend_unavailable') {
    return `Could not ${verb}: the backend is unavailable. Check that Flask is running and retry.`;
  }
  if (response?.error === 'learning_api_unavailable' || response?.status === 404) {
    return action === 'remove'
      ? 'Could not remove the saved correction: it was not found. The mute event was kept.'
      : 'Could not save the correction: the learning endpoint was not found.';
  }
  if (response?.error === 'consent_not_confirmed') {
    return `Could not ${verb}: learning consent is not confirmed for this account.`;
  }
  return `Could not ${verb}. The mute event was kept; retry when the backend is available.`;
}

function appendLearningEventRow(event, { interactive = true, attempts = [event] } = {}) {
  const row = document.createElement('div');
  row.className = `learning-event-row${interactive ? ' learning-event-primary' : ' learning-event-history-row'}`;
  const summary = document.createElement('div');
  const occurrence = `#${event.event_id ?? '?'}`;
  const corrected = event.feedback?.corrected_start_seconds != null
    ? ` → ${formatPlaybackTime(event.feedback.corrected_start_seconds)}–${formatPlaybackTime(event.feedback.corrected_end_seconds)}`
    : '';
  summary.textContent = `${occurrence} ${event.matched_word || 'word'} · ${formatPlaybackTime(event.predicted_start_seconds)}${corrected} · ${event.timing_method || 'estimated'} · ${event.status || 'unknown'}`;
  row.appendChild(summary);

  const controls = document.createElement('div');
  controls.className = 'feedback-choice-group';
  controls.setAttribute('role', 'radiogroup');
  controls.setAttribute('aria-label', `Timing feedback for event ${event.event_id ?? 'unknown'}`);
  ['correct', 'early', 'late', 'missed'].forEach((result) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'feedback-choice';
    button.setAttribute('role', 'radio');
    button.setAttribute('aria-checked', event.feedback?.result === result ? 'true' : 'false');
    button.textContent = `${event.feedback?.result === result ? '✓ ' : ''}${result === 'early' ? 'Too Early'
      : result === 'late' ? 'Too Late'
        : result[0].toUpperCase() + result.slice(1)}`;
    button.addEventListener('click', () => {
      row.dataset.feedbackResult = result;
      controls.querySelectorAll('button').forEach((item) => {
        const selected = item === button;
        item.setAttribute('aria-checked', selected ? 'true' : 'false');
        item.textContent = `${selected ? '✓ ' : ''}${item.dataset.feedbackLabel}`;
      });
      syncCorrectionFieldVisibility(result, start, end);
      if (learningConsentStatus) learningConsentStatus.textContent = `Selected ${result}. Add corrected times if needed, then submit.`;
    });
    button.dataset.feedbackLabel = result === 'early' ? 'Too Early'
      : result === 'late' ? 'Too Late'
        : result[0].toUpperCase() + result.slice(1);
    controls.appendChild(button);
  });
  if (interactive) row.appendChild(controls);

  const start = document.createElement('input');
  start.type = 'number';
  start.min = '0';
  start.step = '0.01';
  start.placeholder = 'Corrected start (seconds)';
  const end = document.createElement('input');
  end.type = 'number';
  end.min = '0';
  end.step = '0.01';
  end.placeholder = 'Corrected end (seconds)';
  if (event.feedback?.corrected_start_seconds != null) start.value = event.feedback.corrected_start_seconds;
  if (event.feedback?.corrected_end_seconds != null) end.value = event.feedback.corrected_end_seconds;
  if (event.feedback?.result) row.dataset.feedbackResult = event.feedback.result;
  syncCorrectionFieldVisibility(event.feedback?.result || '', start, end);
  if (interactive) row.append(start, end);

  const submit = document.createElement('button');
  submit.type = 'button';
  submit.className = 'btn btn-secondary';
  submit.textContent = 'Save correction';
  submit.addEventListener('click', async () => {
    const result = row.dataset.feedbackResult;
    if (!result) {
      if (learningConsentStatus) learningConsentStatus.textContent = 'Choose Correct, Too Early, Too Late, or Missed first.';
      return;
    }
    const feedback = { result };
    if (start.value || end.value) {
      if (!start.value || !end.value || !Number.isFinite(Number(start.value))
        || !Number.isFinite(Number(end.value)) || Number(end.value) <= Number(start.value)) {
        if (learningConsentStatus) learningConsentStatus.textContent = 'Enter both corrected times, with end after start.';
        return;
      }
      feedback.corrected_start_seconds = Number(start.value);
      feedback.corrected_end_seconds = Number(end.value);
    }
    const response = await chrome.runtime.sendMessage({
      type: 'isweep_learning_feedback',
      eventId: event.event_id,
      feedback,
    });
    if (response?.ok) {
      submit.textContent = 'Saved ✓';
      if (learningConsentStatus) learningConsentStatus.textContent = 'Saved ✓';
      await refreshLearningEvents();
    } else if (learningConsentStatus) {
      learningConsentStatus.textContent = learningFeedbackErrorMessage(response, 'save');
    }
  });
  if (interactive) row.appendChild(submit);

  if (interactive && hasSavedFeedback(event)) {
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn-link';
    remove.textContent = 'Remove correction';
    remove.addEventListener('click', async () => {
      const confirmed = typeof globalThis.confirm !== 'function'
        || globalThis.confirm('Remove this saved timing correction? The mute event will remain.');
      if (!confirmed) return;
      const response = await chrome.runtime.sendMessage({
        type: 'isweep_learning_feedback',
        eventId: event.event_id,
        delete: true,
      });
      if (response?.ok) {
        if (learningConsentStatus) learningConsentStatus.textContent = 'Correction removed. The mute event was kept.';
        await refreshLearningEvents();
      } else if (learningConsentStatus) {
        learningConsentStatus.textContent = learningFeedbackErrorMessage(response, 'remove');
      }
    });
    row.appendChild(remove);
  }
  if (!interactive) {
    if (hasSavedFeedback(event)) {
      const manage = document.createElement('details');
      manage.className = 'learning-history-correction';
      const manageSummary = document.createElement('summary');
      manageSummary.textContent = 'Manage saved correction';
      manage.appendChild(manageSummary);
      manage.appendChild(appendLearningEventRow(event, { interactive: true, attempts: [event] }));
      row.appendChild(manage);
    }
    const details = document.createElement('details');
    const detailsSummary = document.createElement('summary');
    detailsSummary.textContent = `${attempts.length} recorded attempt${attempts.length === 1 ? '' : 's'} · event details`;
    details.appendChild(detailsSummary);
    attempts.forEach((attempt) => {
      const item = document.createElement('div');
      item.className = 'learning-event-attempt';
      item.textContent = `Event #${attempt.event_id ?? '?'} · ${formatPlaybackTime(attempt.predicted_start_seconds)} · ${attempt.status || 'unknown'}`;
      details.appendChild(item);
    });
    row.appendChild(details);
  }
  return row;
}

async function refreshLearningEvents() {
  if (!learningEventsList) return;
  const response = await chrome.runtime.sendMessage({ type: 'isweep_learning_list' });
  learningEventsList.textContent = '';
  if (!response?.ok || !Array.isArray(response.events) || !response.events.length) {
    if (response?.error) {
      const messages = {
        unauthorized: 'Learning events unavailable: sign in again.',
        consent_not_confirmed: 'Learning events unavailable: backend consent is not confirmed.',
        learning_api_unavailable: 'Learning events unavailable: API route not found.',
        backend_error: 'Learning events unavailable: backend error.',
        backend_unavailable: 'Learning events unavailable: backend is offline.',
        invalid_response: 'Learning events unavailable: invalid backend response.',
      };
      learningEventsList.textContent = messages[response.error] || 'Learning events unavailable: request failed.';
    } else {
      learningEventsList.textContent = 'No events recorded yet.';
    }
    return;
  }
  const groups = groupLearningEvents(response.events);
  const primary = groups[0];
  learningEventsList.appendChild(appendLearningEventRow(primary.representative, {
    interactive: true,
    attempts: primary.attempts,
  }));
  if (groups.length > 1) {
    const history = document.createElement('details');
    history.className = 'learning-history';
    const historySummary = document.createElement('summary');
    historySummary.textContent = `Show history (${groups.length - 1} other occurrences)`;
    history.appendChild(historySummary);
    groups.slice(1).forEach((group) => history.appendChild(appendLearningEventRow(group.representative, {
      interactive: false,
      attempts: group.attempts,
    })));
    learningEventsList.appendChild(history);
  }
}

async function handleLearningConsentChange() {
  const requested = learningConsentToggle?.checked === true;
  if (learningConsentToggle) learningConsentToggle.disabled = true;
  const response = await chrome.runtime.sendMessage({
    type: 'isweep_set_learning_consent',
    enabled: requested,
  });
  if (response?.ok && response.enabled === requested) {
    setLearningConsentUi(response.enabled);
    if (response.enabled) await refreshLearningEvents();
  } else {
    setLearningConsentUi(!requested, 'Backend did not confirm the learning preference; collection remains unchanged.');
  }
  if (learningConsentToggle) learningConsentToggle.disabled = false;
}

async function handleReportMissedWord() {
  const videoId = learningMissedVideoId?.value.trim();
  const word = learningMissedWord?.value.trim();
  const start = parsePlaybackTime(learningMissedStart?.value);
  const end = parsePlaybackTime(learningMissedEnd?.value);
  if (!videoId || !word || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    if (learningConsentStatus) learningConsentStatus.textContent = 'Enter a video ID, word, and valid start/end times.';
    return;
  }
  const eventResponse = await chrome.runtime.sendMessage({
    type: 'isweep_learning_event',
    event: {
      video_id: videoId,
      matched_word: word,
      caption_source: 'user_report',
      timing_method: 'estimated',
      predicted_start_seconds: start,
      predicted_end_seconds: end,
      playback_speed: 1,
      status: 'skipped',
      playback_context: { paused: false, seeked: false, speed_changed: false },
      dedupe_key: `missed:${videoId}:${word.toLowerCase()}:${start.toFixed(2)}`,
    },
  });
  const eventId = eventResponse?.event?.event_id;
  if (!eventResponse?.ok || !eventId) {
    if (learningConsentStatus) learningConsentStatus.textContent = 'Missed-word report could not be saved.';
    return;
  }
  const feedbackResponse = await chrome.runtime.sendMessage({
    type: 'isweep_learning_feedback',
    eventId,
    feedback: {
      result: 'missed',
      corrected_start_seconds: start,
      corrected_end_seconds: end,
    },
  });
  if (feedbackResponse?.ok) {
    if (learningConsentStatus) learningConsentStatus.textContent = 'Missed-word report saved.';
    await refreshLearningEvents();
  } else if (learningConsentStatus) {
    learningConsentStatus.textContent = 'Event saved, but its feedback could not be saved. You can retry from Recent Mute Events.';
    await refreshLearningEvents();
  }
}

/**
 * Extract initials from a name or email
 * @param {string} name - Name or email to extract initials from
 * @returns {string} Initials (up to 2 characters)
 */
function getInitials(name) {
  if (!name) return '--';
  
  const parts = name.split(/[\s@._-]+/).filter(p => p.length > 0); // Split on common separators
  
  if (parts.length === 0) return '--';
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase(); // First two letters
  
  return (parts[0][0] + parts[1][0]).toUpperCase(); // First letters of first two parts
}

/**
 * Set up all event listeners for buttons and links
 */
function setupEventListeners() {
  // Logged Out State Events
  btnLogin.addEventListener('click', handleLoginClick); // Open login flow
  linkCreateAccount.addEventListener('click', handleCreateAccountClick); // Open account creation
  btnQuickLogin.addEventListener('click', handleQuickLogin); // Submit quick login
  if (btnCreateLocalDevAccount) {
    btnCreateLocalDevAccount.addEventListener('click', handleCreateLocalDevAccount);
  }
  btnCancelQuickLogin.addEventListener('click', handleCancelQuickLogin); // Cancel quick login
  
  // Logged In State Events
  btnOpenSettings.addEventListener('click', handleOpenSettings); // Open filters/settings page
  if (btnSyncPrefs) {
    btnSyncPrefs.addEventListener('click', handleSyncPrefs); // Trigger prefs sync
  }
  linkResetFilters.addEventListener('click', handleResetFilters); // Open reset filters section
  linkManageAccount.addEventListener('click', handleManageAccount); // Open account page
  linkLogout.addEventListener('click', handleLogout); // Log out
  if (learningConsentToggle) learningConsentToggle.addEventListener('change', handleLearningConsentChange);
  if (btnReportMissedWord) btnReportMissedWord.addEventListener('click', handleReportMissedWord);
  if (btnLearningMissedStartNow) btnLearningMissedStartNow.addEventListener('click', () => captureCurrentVideoTime(learningMissedStart));
  if (btnLearningMissedEndNow) btnLearningMissedEndNow.addEventListener('click', () => captureCurrentVideoTime(learningMissedEnd));

  if (btnCleanCaptionsToggle) {
    btnCleanCaptionsToggle.addEventListener('click', async () => {
      const next = {
        ...cleanCaptionSettingsCache,
        cleanCaptionsEnabled: !cleanCaptionSettingsCache.cleanCaptionsEnabled,
      };
      await saveCleanCaptionSettings(next);
    });
  }
  if (btnCaptionAppearance && captionSettingsPanel) {
    btnCaptionAppearance.addEventListener('click', () => {
      const willShow = captionSettingsPanel.classList.contains('hidden');
      captionSettingsPanel.classList.toggle('hidden', !willShow);
      btnCaptionAppearance.setAttribute('aria-expanded', willShow ? 'true' : 'false');
    });
  }
  if (cleanCaptionStyleSelect) {
    cleanCaptionStyleSelect.addEventListener('change', async () => {
      await saveCleanCaptionSettings({
        ...cleanCaptionSettingsCache,
        cleanCaptionStyle: cleanCaptionStyleSelect.value,
      });
    });
  }
  if (cleanCaptionTextSizeSelect) {
    cleanCaptionTextSizeSelect.addEventListener('change', async () => {
      await saveCleanCaptionSettings({
        ...cleanCaptionSettingsCache,
        cleanCaptionTextSize: cleanCaptionTextSizeSelect.value,
      });
    });
  }
  if (cleanCaptionWordMuteModeSelect) {
    cleanCaptionWordMuteModeSelect.addEventListener('change', async () => {
      await saveCleanCaptionSettings({
        ...cleanCaptionSettingsCache,
        cleanCaptionWordMuteMode: cleanCaptionWordMuteModeSelect.value,
      });
    });
  }
  if (btnResetCaptionPosition) {
    btnResetCaptionPosition.addEventListener('click', async () => {
      await saveCleanCaptionSettings({
        ...cleanCaptionSettingsCache,
        cleanCaptionPosition: { ...CLEAN_CAPTION_DEFAULTS.cleanCaptionPosition },
      });
    });
  }
  
  // Allow Enter key in email input
  emailInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      handleQuickLogin();
    }
  });
  if (passwordInput) {
    passwordInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        handleQuickLogin();
      }
    });
  }
}

async function initCleanCaptionControls() {
  const store = await chrome.storage.local.get([STORAGE_KEYS.CLEAN_CAPTION_SETTINGS]);
  cleanCaptionSettingsCache = normalizeCleanCaptionSettings(store[STORAGE_KEYS.CLEAN_CAPTION_SETTINGS]);
  renderCleanCaptionControls();

  // Keep runtime capture state aligned with persisted [CC] toggle.
  // If the service worker restarted while [CC] stayed enabled, re-send start.
  try {
    await chrome.runtime.sendMessage({
      type: 'isweep_caption_capture_control',
      enabled: cleanCaptionSettingsCache.cleanCaptionsEnabled === true,
    });
  } catch (_) {
    // Best effort. Popup still reflects current persisted settings.
  }
}

function renderCleanCaptionControls() {
  if (btnCleanCaptionsToggle) {
    btnCleanCaptionsToggle.dataset.enabled = cleanCaptionSettingsCache.cleanCaptionsEnabled ? 'true' : 'false';
    btnCleanCaptionsToggle.setAttribute('aria-pressed', cleanCaptionSettingsCache.cleanCaptionsEnabled ? 'true' : 'false');
    btnCleanCaptionsToggle.textContent = '[CC]';
    btnCleanCaptionsToggle.setAttribute(
      'aria-label',
      cleanCaptionSettingsCache.cleanCaptionsEnabled ? 'Clean captions on' : 'Clean captions off'
    );
  }
  if (cleanCaptionStyleSelect) {
    cleanCaptionStyleSelect.value = cleanCaptionSettingsCache.cleanCaptionStyle;
  }
  if (cleanCaptionTextSizeSelect) {
    cleanCaptionTextSizeSelect.value = cleanCaptionSettingsCache.cleanCaptionTextSize;
  }
  if (cleanCaptionWordMuteModeSelect) {
    cleanCaptionWordMuteModeSelect.value = cleanCaptionSettingsCache.cleanCaptionWordMuteMode;
  }
}

async function saveCleanCaptionSettings(nextSettings) {
  cleanCaptionSettingsCache = normalizeCleanCaptionSettings(nextSettings);
  await chrome.storage.local.set({
    [STORAGE_KEYS.CLEAN_CAPTION_SETTINGS]: cleanCaptionSettingsCache,
  });
  try {
    await chrome.runtime.sendMessage({
      type: cleanCaptionSettingsCache.cleanCaptionsEnabled === true
        ? 'isweep_start_audio_captions'
        : 'isweep_stop_audio_captions',
    });
  } catch (_) {
    // Best effort: content script also reacts to storage changes.
  }
  await notifyActiveYouTubeTabCleanCaptionSettings(cleanCaptionSettingsCache);
  renderCleanCaptionControls();
  await refreshCaptionRuntimeStatus();
  console.log(LOG_PREFIX, 'clean caption settings saved', cleanCaptionSettingsCache);
}

async function notifyActiveYouTubeTabCleanCaptionSettings(settings) {
  try {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab?.id) return;
    if (!/youtube\.com\/watch/i.test(String(activeTab.url || ''))) return;
    await chrome.tabs.sendMessage(activeTab.id, {
      type: 'isweep_clean_caption_settings_changed',
      settings,
    });
  } catch (_) {
    // Best effort: content script may not be ready yet; storage.onChanged is fallback.
  }
}

async function handleSyncPrefs(e) {
  if (e) e.preventDefault();
  console.log(LOG_PREFIX, 'prefs sync start');
  try {
    const preStore = await chrome.storage.local.get([
      TOKEN_KEY,
      STORAGE_KEYS.DEV_LOCAL_AUTH,
      STORAGE_KEYS.BACKEND_URL,
      STORAGE_KEYS.PREFS,
    ]);
    const devLocalAuthActive = preStore[STORAGE_KEYS.DEV_LOCAL_AUTH] === true
      && isLocalBackendUrl(preStore[STORAGE_KEYS.BACKEND_URL] || 'http://127.0.0.1:5000');

    // Ask the active tab (site) to push its token into extension storage.
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTab?.id) {
      try {
        await chrome.tabs.sendMessage(activeTab.id, { type: 'ISWEEP_PULL_TOKEN' });
      } catch (_) {
        // ignore; fallback to whatever is already in storage
      }
    }

    // Pull token from storage using the canonical key.
    const store = await chrome.storage.local.get([TOKEN_KEY]);
    const token = store[TOKEN_KEY];

    if (!token) {
      if (devLocalAuthActive) {
        console.log('[ISWEEP][AUTH] dev local auth enabled');
        console.log('[ISWEEP][AUTH] using local preferences fallback');
        setSyncPrefsAvailability(false);
        if (signedInStatus) {
          signedInStatus.textContent = preStore[STORAGE_KEYS.PREFS]
            ? 'Dev local auth enabled. Using cached preferences.'
            : 'Dev local auth enabled. No cached preferences yet.';
        }
        return;
      }
      console.warn(LOG_PREFIX, 'prefs sync failed', 'missing token');
      setSyncPrefsAvailability(false);
      if (signedInStatus) {
        signedInStatus.textContent = 'Captions active. Sign in to sync preferences.';
      }
      return;
    }

    // Refresh canonical token key in storage for background fetch logic.
    await chrome.storage.local.set({ [TOKEN_KEY]: token });
    setSyncPrefsAvailability(true);

    const res = await chrome.runtime
      .sendMessage({ type: 'isweep_sync_prefs' })
      .catch((err) => {
        console.error(LOG_PREFIX, 'Runtime message failed:', err);
        return { ok: false, error: 'background not available' };
      });
    if (!res || !res.ok) {
      console.warn(LOG_PREFIX, 'prefs sync failed', res?.error || 'unknown');
      alert('Sync failed. Are you logged in?');
      return;
    }
    console.log(LOG_PREFIX, 'prefs sync success', res.status || '');
    const synced = await chrome.storage.local.get([
      STORAGE_KEYS.PREFS,
      STORAGE_KEYS.LEARNING_CONSENT_CONFIRMED,
    ]);
    const learningEnabled = synced[STORAGE_KEYS.LEARNING_CONSENT_CONFIRMED] === true
      && synced[STORAGE_KEYS.PREFS]?.learning?.enabled === true;
    setLearningConsentUi(learningEnabled);
    if (learningEnabled) await refreshLearningEvents();
    alert('Preferences synced.');
  } catch (err) {
    console.error(LOG_PREFIX, 'prefs sync failed', err);
    alert('Sync failed.');
  }
}

/**
 * Handle "Log in with Email" button click
 * Opens web app login page in new tab and shows quick login form
 */
function handleLoginClick(e) {
  e.preventDefault();
  console.log(LOG_PREFIX, 'login button clicked');

  // Show quick login form inside popup
  quickLoginForm.classList.remove('hidden');
  emailInput.focus();
}

/**
 * Handle "Create one here" link click
 * Opens web app account creation page
 */
function handleCreateAccountClick(e) {
  e.preventDefault();
  console.log(LOG_PREFIX, 'create account link clicked');
  getPreferredFrontendBaseUrl()
    .then((base) => {
      chrome.tabs.create({ url: `${base}/Account.html#create` });
    })
    .catch(() => {
      chrome.tabs.create({ url: `${DEFAULT_LOCAL_FRONTEND_BASE}/Account.html#create` });
    });
}

async function handleCreateLocalDevAccount() {
  const email = emailInput.value.trim();
  const password = (passwordInput?.value || '').trim();

  if (!email || !email.includes('@') || !password) {
    alert('Enter email and password to create a local dev account.');
    return;
  }

  const backendUrl = await getBackendUrl();
  if (!isLocalBackendUrl(backendUrl)) {
    alert('Local dev account creation is only available with local backend.');
    return;
  }

  const payload = { email, password };
  let responseBody = null;
  try {
    const signup = await fetch(`${backendUrl}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (signup.ok) {
      responseBody = await signup.json().catch(() => ({}));
    } else if (signup.status === 409) {
      const login = await fetch(`${backendUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!login.ok) {
        const body = await login.text();
        throw new Error(body || `status ${login.status}`);
      }
      responseBody = await login.json().catch(() => ({}));
    } else {
      const body = await signup.text();
      throw new Error(body || `status ${signup.status}`);
    }

    if (!responseBody?.token) {
      throw new Error('Missing token in auth response');
    }

    const displayName = email.split('@')[0];
    const authData = {
      email,
      displayName,
      initials: getInitials(displayName),
      loggedInAt: new Date().toISOString(),
    };

    await chrome.storage.local.set({
      [TOKEN_KEY]: responseBody.token,
      [STORAGE_KEYS.USER_ID]: responseBody.user_id,
      [STORAGE_KEYS.AUTH]: authData,
      [STORAGE_KEYS.ENABLED]: true,
    });
    setSyncPrefsAvailability(true);
    renderLoggedInState(authData, true);
    if (signedInStatus) {
      signedInStatus.textContent = 'Signed in. Preferences can now sync.';
    }

    quickLoginForm.classList.add('hidden');
    emailInput.value = '';
    if (passwordInput) passwordInput.value = '';
    console.log(LOG_PREFIX, 'local dev account ready');
  } catch (error) {
    console.warn(LOG_PREFIX, 'local dev account creation failed', error?.message || error);
    alert('Local dev account creation failed. Please verify backend and credentials.');
  }
}

/**
 * Handle quick login (development mode)
 * Saves email to chrome.storage.local and renders logged in state
 */
async function handleQuickLogin() {
  const email = emailInput.value.trim();
  const password = (passwordInput?.value || '').trim();

  if (!email || !email.includes('@') || !password) {
    alert('Please enter email and password.');
    return;
  }

  console.log(LOG_PREFIX, 'login start');

  try {
    const response = await chrome.runtime
      .sendMessage({
        type: 'isweep_login',
        email,
        password,
      })
      .catch((err) => {
        console.error(LOG_PREFIX, 'Runtime message failed:', err);
        return { ok: false, error: 'background not available' };
      });
    if (!response || !response.ok) {
      console.warn(LOG_PREFIX, 'login failed', response?.error || 'unknown');
      const errorText = String(response?.error || '').toLowerCase();
      if (errorText.includes('invalid credentials')) {
        alert('Login failed: invalid credentials for this backend. If using local backend, create a local account first.');
      } else {
        alert(`Login failed. ${response?.error || 'Please check your credentials and backend URL.'}`);
      }
      return;
    }
    console.log('[ISWEEP][POPUP] login success', response.status || '');

    const displayName = email.split('@')[0];
    const initials = getInitials(displayName);
    const authData = {
      email,
      displayName,
      initials,
      loggedInAt: new Date().toISOString(),
    };

    await saveAuthSession({ authData });
    // Reflect prefs presence after background login
    const store = await chrome.storage.local.get([STORAGE_KEYS.PREFS]);
    if (signedInStatus) {
      signedInStatus.textContent = store[STORAGE_KEYS.PREFS]
        ? 'Signed in. Preferences cached.'
        : 'Signed in. No preferences cached yet (open Filters and Save).';
    }
    setSyncPrefsAvailability(true);
    renderLoggedInState(authData, true);

    quickLoginForm.classList.add('hidden');
    emailInput.value = '';
    if (passwordInput) passwordInput.value = '';
  } catch (error) {
    console.error(LOG_PREFIX, 'login failed', error);
    alert('Login failed. Please check your credentials and backend URL.');
  }
}

/**
 * Handle cancel quick login
 */
function handleCancelQuickLogin(e) {
  e.preventDefault();
  quickLoginForm.classList.add('hidden');
  emailInput.value = '';
}

/**
 * Handle "Open Filters" button click
 * Opens ISweep Filters page in new tab
 */
async function handleOpenSettings(e) {
  e.preventDefault();
  console.log(LOG_PREFIX, 'opening Filters page');
  const base = await getFrontendBaseUrl();
  chrome.tabs.create({ url: `${base}/Filter.html` });
}

/**
 * Handle "Reset Filters" link click
 * Opens Filters page with filters section anchor
 */
async function handleResetFilters(e) {
  e.preventDefault();
  console.log(LOG_PREFIX, 'opening Reset Filters');
  const base = await getFrontendBaseUrl();
  chrome.tabs.create({ url: `${base}/Filter.html#filters` });
}

/**
 * Handle "Manage Account" link click
 * Opens Account page
 */
async function handleManageAccount(e) {
  e.preventDefault();
  console.log(LOG_PREFIX, 'opening Manage Account');
  const base = await getPreferredFrontendBaseUrl();
  chrome.tabs.create({ url: `${base}/Account.html` });
}

/**
 * Handle "Log Out" link click
 * Clears auth data and renders logged out state
 */
async function handleLogout(e) {
  e.preventDefault();
  console.log(LOG_PREFIX, 'logging out');
  
  try {
    // Remove auth data from storage
    await chrome.storage.local.remove([
      STORAGE_KEYS.AUTH,
      STORAGE_KEYS.USER_ID,
      STORAGE_KEYS.PREFS,
      TOKEN_KEY,
      STORAGE_KEYS.LEARNING_CONSENT_CONFIRMED,
    ]);
    setSyncPrefsAvailability(false);
    
    console.log('[ISWEEP][POPUP] Logged out successfully');
    
    // Render logged out state
    renderLoggedOutState();
    
  } catch (error) {
    console.error('[ISweep Popup] Error logging out:', error);
    alert('Failed to log out. Please try again.');
  }
}

if (typeof globalThis !== 'undefined' && globalThis.__ISWEEP_TEST_MODE__) {
  globalThis.__ISWEEP_POPUP_TEST_HOOKS__ = {
    parsePlaybackTime,
    formatPlaybackTime,
    eventOccurrenceKey,
    groupLearningEvents,
    hasSavedFeedback,
    learningFeedbackErrorMessage,
    getActiveVideoClock,
    captureCurrentVideoTime,
  };
}
