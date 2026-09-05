/**
 * ISWEEP COMPONENT: Frontend demo logic for settings, auth, and plan selection.
 *
 * This script powers the static docs site: toggles themes, simulates auth, reads/writes
 * preferences, and exercises backend endpoints for login/signup/preferences. It shares
 * token keys with the extension bridge so the same token can be reused by the Chrome extension.
 *
 * System connection:
 *   Docs UI -> fetch auth/preferences -> backend (http://127.0.0.1:5000) -> store token in localStorage
 *   Token is reused by the extension to call /event while watching captions.
 */
const CURRENT_PLAN_KEY = "currentPlan"; // Stores the selected plan in localStorage so plan info persists.
const SETTINGS_KEY = "isweep-settings"; // Stores settings payloads in localStorage for the settings page demo.
const themePreferenceKey = 'isweep-theme'; // Stores the user’s theme preference so it survives reloads.
const themeLabelMap = { light: 'Light Mode', dark: 'Dark Mode' }; // Maps preference keys to human-friendly labels for the dropdown text.
const authStateKey = 'auth-state'; // Stores { name, email, token } as a placeholder auth state until backend exists.
const backendUrlKey = 'isweep-backend-url'; // Allows overriding the backend URL for local dev.
const tokenStorageKey = 'isweep-token'; // Stores auth token from backend.
const userIdStorageKey = 'isweep-user-id'; // Stores user id returned by backend.
const preferencesCacheKey = 'isweep-preferences'; // Caches preferences for offline fallback.
const TOKEN_KEY = 'isweep_auth_token'; // Unified token key shared with extension bridge.
const LANGUAGE_WORDLIST_URL = 'wordlists/language_words.json'; // Predefined language words per subfilter.
const LANGUAGE_WORDLIST_MIGRATION_KEY = 'isweep-language-wordlist-v2'; // One-time migration so newly added default language words become selected for existing users.
const LANGUAGE_WORDLIST_NEW_DEFAULT_IDS = {
  profanity: Array.from({ length: 19 }, (_, index) => `profanity-${index + 15}`),
  blasphemy: ['blasphemy-7', 'blasphemy-8', 'blasphemy-9'],
};
const wordLibrary = { language: {} }; // Loaded word lists by category/subfilter.
let expandedSubfilterKey = null; // Tracks which subfilter panel is open.
const BACKEND_DEFAULT = 'http://127.0.0.1:5000';
const FILTER_CATEGORY_CONFIG = {
  language: {
    label: 'Language',
    icon: '💬',
    subcategories: [
      { key: 'profanity', label: 'Profanity', count: '33/33' },
      { key: 'blasphemy', label: 'Blasphemy', count: '9/9' },
      { key: 'childish', label: 'Childish', count: '4/4' },
      { key: 'slurs', label: 'Slurs', count: '12/12' },
    ],
    defaults: { action: 'mute', duration: 6, sensitivity: 3 },
  },
  intimacy: {
    label: 'Intimacy',
    icon: '❤️',
    subcategories: [
      { key: 'kissing', label: 'Kissing', count: '5/5' },
      { key: 'nudity', label: 'Nudity', count: '8/8' },
      { key: 'suggestive', label: 'Suggestive', count: '7/7' },
      { key: 'assault', label: 'Assault', count: '3/3' },
    ],
    defaults: { action: 'skip', duration: 15, sensitivity: 3 },
  },
  violence: {
    label: 'Violence',
    icon: '⚔️',
    subcategories: [
      { key: 'combat', label: 'Combat', count: '9/9' },
      { key: 'weapons', label: 'Weapons', count: '6/6' },
      { key: 'blood', label: 'Blood', count: '5/5' },
      { key: 'gore', label: 'Gore', count: '4/4' },
    ],
    defaults: { action: 'skip', duration: 12, sensitivity: 3 },
  },
  substances: {
    label: 'Substances',
    icon: '🍷',
    subcategories: [
      { key: 'alcohol', label: 'Alcohol', count: '6/6' },
      { key: 'drugs', label: 'Drugs', count: '5/5' },
      { key: 'smoking', label: 'Smoking', count: '4/4' },
      { key: 'gambling', label: 'Gambling', count: '3/3' },
    ],
    defaults: { action: 'log-only', duration: 6, sensitivity: 2 },
  },
  horror: {
    label: 'Horror & Fears',
    icon: '👻',
    subcategories: [
      { key: 'jump_scares', label: 'Jump scares', count: '6/6' },
      { key: 'creatures', label: 'Creatures', count: '4/4' },
      { key: 'supernatural', label: 'Supernatural', count: '5/5' },
      { key: 'suspense', label: 'Suspense', count: '4/4' },
    ],
    defaults: { action: 'fast-forward', duration: 10, sensitivity: 2 },
  },
};

// Migration: copy older camelCase keys into the new kebab-case keys so existing users stay signed in.
if (!localStorage.getItem(tokenStorageKey) && localStorage.getItem('isweepToken')) {
  localStorage.setItem(tokenStorageKey, localStorage.getItem('isweepToken'));
}
if (!localStorage.getItem(userIdStorageKey) && localStorage.getItem('isweepUserId')) {
  localStorage.setItem(userIdStorageKey, localStorage.getItem('isweepUserId'));
}

// Keep the website's legacy token key and the shared extension/DVD key aligned.
// Prefer the shared key when both exist so a stale legacy value cannot switch
// the Filters page to a different account.
const sharedTokenAtLoad = localStorage.getItem(TOKEN_KEY);
const legacyTokenAtLoad = localStorage.getItem(tokenStorageKey);
if (sharedTokenAtLoad) {
  localStorage.setItem(tokenStorageKey, sharedTokenAtLoad);
} else if (legacyTokenAtLoad) {
  localStorage.setItem(TOKEN_KEY, legacyTokenAtLoad);
}

const authModal = document.getElementById('authModal');
const authBackdrop = authModal ? authModal.querySelector('.auth-backdrop') : null;
const authPanels = authModal ? authModal.querySelectorAll('[data-auth-panel]') : [];
const accountSummary = authModal ? authModal.querySelector('#accountSummary') : null;
const signInForm = authModal ? authModal.querySelector('#signInForm') : null;
const createAccountForm = authModal ? authModal.querySelector('#createAccountForm') : null;
const themeToggleDropdown = document.getElementById('themeToggleDropdown');
const kbToggle = document.getElementById('kbToggle');
const kbDropdown = document.getElementById('kbDropdown');
const kbWrapper = document.querySelector('.kb-wrapper');
const signedInBlock = document.querySelector('[data-auth-signed-in]');
const signedOutBlock = document.querySelector('[data-auth-signed-out]');
const authLaunchers = document.querySelectorAll('[data-open-auth]');
const authSwitchers = document.querySelectorAll('[data-switch-auth]');
const logoutButtons = document.querySelectorAll('[data-logout]');
const userMenu = document.querySelector('.user-menu');

const authState = {
  get() {
    try {
      const raw = localStorage.getItem(authStateKey);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      console.error('Failed to parse auth state', error);
      return null;
    }
  },
  set(state) {
    localStorage.setItem(authStateKey, JSON.stringify(state));
  },
  clear() {
    localStorage.removeItem(authStateKey);
  },
};

function deriveInitials(name, email) {
  const source = name || email || '';
  const parts = source.split(/[^A-Za-z0-9]+/).filter(Boolean);
  if (parts.length === 0) return 'KB';
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function setKbAvatarInitials(state) {
  const avatars = document.querySelectorAll('.kb-avatar');
  if (!avatars.length) return;
  const initials = state?.initials || deriveInitials(state?.name, state?.email);
  avatars.forEach((el) => {
    el.textContent = initials || 'KB';
  });
}

function getBackendUrl() {
  const override = localStorage.getItem(backendUrlKey);
  return override || BACKEND_DEFAULT;
}

function applyThemePreference(preference) {
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const resolvedTheme = preference === 'system'
    ? (prefersDark ? 'dark' : 'light')
    : preference;

  document.documentElement.classList.toggle('dark', resolvedTheme === 'dark');
  document.documentElement.setAttribute('data-theme', resolvedTheme);
  localStorage.setItem(themePreferenceKey, preference);

  if (themeToggleDropdown) {
    const label = resolvedTheme === 'dark'
      ? themeLabelMap.light
      : themeLabelMap.dark;
    themeToggleDropdown.textContent = label || 'Toggle Theme';
    themeToggleDropdown.setAttribute(
      'aria-label',
      `Switch to ${label || 'alternate'} theme`
    );
  }
}

function showAuthPanel(panel) {
  if (!authModal) return;

  authPanels.forEach((p) => {
    p.style.display =
      p.getAttribute('data-auth-panel') === panel ? 'block' : 'none';
  });

  authModal.style.display = 'block';
}

function closeAuth() {
  if (!authModal) return;
  authModal.style.display = 'none';
}

function syncAuthUI() {
  const state = authState.get();
  const isSignedIn = Boolean(state);

  if (signedInBlock && signedOutBlock) {
    signedInBlock.style.display = isSignedIn ? 'block' : 'none';
    signedOutBlock.style.display = isSignedIn ? 'none' : 'block';

    if (state) {
      const accountName = signedInBlock.querySelector('.account-name');
      const accountEmail = signedInBlock.querySelector('.account-email');

      if (accountName) {
        accountName.textContent = state.name || 'Welcome back';
      }

      if (accountEmail) {
        accountEmail.textContent = state.email || '';
      }
    }
  }

  if (accountSummary) {
    accountSummary.textContent = state
      ? `${state.name || 'Account'}, ${state.email || ''}`
      : 'Not signed in.';
  }

  setKbAvatarInitials(state);
}

async function callAuthEndpoint(path, payload) {
  const res = await fetch(`${getBackendUrl()}/auth/${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (res.status !== 200 && res.status !== 201) {
    const message = await res.text();
    throw new Error(message || 'Authentication failed');
  }

  return res.json();
}

function persistSession({ token, userId, email, name, initials }) {
  localStorage.setItem(tokenStorageKey, token);
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(userIdStorageKey, userId);

  const resolvedName = name || email.split('@')[0] || 'User';

  authState.set({
    name: resolvedName,
    email,
    token,
    initials: initials || deriveInitials(resolvedName, email),
  });

  setKbAvatarInitials(authState.get());
}

function clearSession() {
  localStorage.removeItem(tokenStorageKey);
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(userIdStorageKey);
  authState.clear();
}

const savedThemePreference =
  localStorage.getItem(themePreferenceKey) || 'light';

applyThemePreference(savedThemePreference);

if (themeToggleDropdown) {
  themeToggleDropdown.addEventListener('click', () => {
    const current = localStorage.getItem(themePreferenceKey) || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    applyThemePreference(next);

    if (kbDropdown) {
      kbDropdown.classList.add('hidden');
    }
  });
}

if (kbToggle && kbDropdown) {
  kbToggle.addEventListener('click', (e) => {
    e.preventDefault();
    kbDropdown.classList.toggle('hidden');
  });

  document.addEventListener('click', (event) => {
    if (!kbWrapper) return;

    const isInside = kbWrapper.contains(event.target);

    if (!isInside) {
      kbDropdown.classList.add('hidden');
    }
  });
}

if (authLaunchers.length && authModal) {
  authLaunchers.forEach((trigger) => {
    trigger.addEventListener('click', () => {
      const panel = trigger.getAttribute('data-open-auth') || 'signin';
      showAuthPanel(panel);
    });
  });
}

if (authSwitchers.length) {
  authSwitchers.forEach((switcher) => {
    switcher.addEventListener('click', () => {
      const target = switcher.getAttribute('data-switch-auth');

      if (target) {
        showAuthPanel(target);
      }
    });
  });
}

if (logoutButtons.length) {
  logoutButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      clearSession();
      syncAuthUI();
      closeAuth();

      if (userMenu) {
        userMenu.open = false;
      }
    });
  });
}

if (authBackdrop) {
  authBackdrop.addEventListener('click', (event) => {
    if (
      event.target === authBackdrop ||
      event.target.hasAttribute('data-close-auth')
    ) {
      closeAuth();
    }
  });
}

if (authModal) {
  document.addEventListener('keydown', (event) => {
    if (
      event.key === 'Escape' &&
      authModal.style.display === 'block'
    ) {
      closeAuth();
    }
  });
}

if (signInForm) {
  signInForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(signInForm);

    const payload = {
      email: formData.get('email'),
      password: formData.get('password'),
    };

    try {
      const result = await callAuthEndpoint('login', payload);

      persistSession({
        token: result.token,
        userId: result.user_id,
        email: payload.email,
      });

      await fetchAndCachePreferences();
      syncAuthUI();
      closeAuth();
    } catch (error) {
      console.error('[ISWEEP] Login failed', error);
      alert('Login failed. Please check your email/password and try again.');
    }
  });
}

if (createAccountForm) {
  createAccountForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(createAccountForm);

    const payload = {
      name: formData.get('name'),
      email: formData.get('email'),
      password: formData.get('password'),
      confirm: formData.get('confirm'),
    };

    if (payload.password !== payload.confirm) {
      alert('Passwords do not match.');
      return;
    }

    try {
      const result = await callAuthEndpoint('signup', payload);

      persistSession({
        token: result.token,
        userId: result.user_id,
        email: payload.email,
        name: payload.name,
      });

      await fetchAndCachePreferences();
      syncAuthUI();
      closeAuth();
    } catch (error) {
      console.error('[ISWEEP] Signup failed', error);
      alert('Signup failed. Please try again.');
    }
  });
}

syncAuthUI();

//-----------------------------------------------------
//  ISWEEP PLAN SYSTEM
//-----------------------------------------------------

const PLAN_CONFIGS = {
  free: {
    key: "free",
    label: "Free Tier",
  },
  flexible: {
    key: "flexible",
    label: "Flexible Subscription",
  },
  full: {
    key: "full",
    label: "Full Ownership",
  },
};

function planHasFiltering(planKey) {
  // Developer mode: allow all plans to use filtering.
  return true;

  // Production:
  // return planKey === "flexible" || planKey === "full";
}

function selectPlan(planKey) {
  const planConfig = PLAN_CONFIGS[planKey];

  if (!planConfig) return;

  localStorage.setItem(
    CURRENT_PLAN_KEY,
    JSON.stringify(planConfig)
  );

  window.location.href = "Account.html";
}

//-----------------------------------------------------
//  HOOK PLAN BUTTONS
//-----------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const btnFree = document.getElementById("planFreeBtn");
  const btnFlexible = document.getElementById("planFlexibleBtn");
  const btnFull = document.getElementById("planFullBtn");

  if (btnFree) {
    btnFree.addEventListener("click", (e) => {
      e.preventDefault();
      selectPlan("free");
    });
  }

  if (btnFlexible) {
    btnFlexible.addEventListener("click", (e) => {
      e.preventDefault();
      selectPlan("flexible");
    });
  }

  if (btnFull) {
    btnFull.addEventListener("click", (e) => {
      e.preventDefault();
      selectPlan("full");
    });
  }
});

//-----------------------------------------------------
//  ACCOUNT PAGE DISPLAY
//-----------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const displayElement =
    document.getElementById("current-plan-display");

  const inputElement =
    document.querySelector('input[name="plan"]');

  try {
    const planData =
      localStorage.getItem(CURRENT_PLAN_KEY);

    let plan = null;

    if (planData) {
      try {
        plan = JSON.parse(planData);
      } catch (err) {
        plan = {
          label: planData,
        };
      }
    }

    const planLabel =
      plan
        ? plan.label
        : "No plan selected yet";

    if (displayElement) {
      displayElement.textContent =
        planLabel;
    }

    if (inputElement) {
      inputElement.value =
        planLabel;

      if (!plan) {
        inputElement.placeholder =
          "No plan selected yet";
      }
    }
  } catch (err) {
    console.error(
      "Failed to load plan from localStorage",
      err
    );

    if (displayElement) {
      displayElement.textContent =
        "No plan selected yet";
    }

    if (inputElement) {
      inputElement.placeholder =
        "No plan selected yet";
    }
  }
});

//-----------------------------------------------------
//  CHECK IF FILTERING IS ENABLED
//-----------------------------------------------------

function isFilteringEnabled() {
  try {
    const planData =
      localStorage.getItem(CURRENT_PLAN_KEY);

    const plan =
      planData
        ? JSON.parse(planData)
        : null;

    const planKey =
      plan
        ? plan.key
        : "free";

    return planHasFiltering(planKey);
  } catch (err) {
    console.error(
      "Failed to check filtering status",
      err
    );

    return planHasFiltering("free");
  }
}

//-----------------------------------------------------
// SETTINGS PAGE → LOCAL STORAGE + /preferences
//-----------------------------------------------------

function loadSettingsFromStorage() {
  try {
    const raw =
      localStorage.getItem(SETTINGS_KEY);

    if (!raw) {
      return {};
    }

    return JSON.parse(raw);
  } catch (err) {
    console.error(
      "Failed to read settings from localStorage",
      err
    );

    return {};
  }
}

function saveSettingsToStorage(settings) {
  try {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify(settings)
    );
  } catch (err) {
    console.error(
      "Failed to save settings to localStorage",
      err
    );
  }
}

function getDefaultFilterState() {
  const base = {
    filters_enabled: {},
    subfilters_enabled: {},
    actions: {},
    custom_words: {
      language: [],
    },
    predefined_words: {
      language: {},
    },
  };

  Object.entries(FILTER_CATEGORY_CONFIG).forEach(
    ([key, config]) => {
      base.filters_enabled[key] = true;
      base.subfilters_enabled[key] = {};

      config.subcategories.forEach((sub) => {
        base.subfilters_enabled[key][sub.key] = true;
      });

      base.actions[key] = {
        action: config.defaults.action,
        duration: config.defaults.duration,
        sensitivity: config.defaults.sensitivity,
      };
    }
  );

  return base;
}

function ensureFilterSettings(settings) {
  const defaults =
    getDefaultFilterState();

  const merged = {
    ...settings,
  };

  merged.filters_enabled = {
    ...defaults.filters_enabled,
    ...(settings.filters_enabled || {}),
  };

  merged.subfilters_enabled = {
    ...defaults.subfilters_enabled,
    ...(settings.subfilters_enabled || {}),
  };

  merged.actions = {
    ...defaults.actions,
    ...(settings.actions || {}),
  };

  merged.custom_words = {
    ...defaults.custom_words,
    ...(settings.custom_words || {}),
  };

  merged.predefined_words = {
    ...defaults.predefined_words,
    ...(settings.predefined_words || {}),
  };

  Object.keys(FILTER_CATEGORY_CONFIG).forEach((key) => {
    merged.subfilters_enabled[key] = {
      ...defaults.subfilters_enabled[key],
      ...(merged.subfilters_enabled[key] || {}),
    };

    merged.actions[key] = {
      ...defaults.actions[key],
      ...(merged.actions[key] || {}),
    };

    merged.custom_words[key] =
      key === 'language' &&
      Array.isArray(merged.custom_words[key])
        ? merged.custom_words[key]
        : key === 'language'
          ? []
          : undefined;

    merged.predefined_words[key] =
      merged.predefined_words[key] || {};

    if (key === 'language') {
      Object.entries(
        wordLibrary.language || {}
      ).forEach(([subKey, payload]) => {
        const items =
          Array.isArray(payload?.items)
            ? payload.items
            : [];

        ensurePredefinedSelection(
          merged,
          'language',
          subKey,
          items
        );
      });
    }
  });

  return merged;
}

function maskTokenForDisplay(token) {
  const word =
    token || '';

  const len =
    word.length;

  if (len === 0) {
    return '';
  }

  if (len <= 2) {
    return `${word[0]}*`;
  }

  if (len === 3) {
    return `${word[0]}*${word[2]}`;
  }

  if (len === 4) {
    return `${word.slice(0, 2)}*${word[3]}`;
  }

  return `${word.slice(0, 2)}***${word[len - 1]}`;
}

function maskWordPreservingNonLetters(word) {
  return word
    .split(' ')
    .map((chunk) =>
      maskTokenForDisplay(chunk)
    )
    .join(' ');
}

function getSelectedPredefinedWords(settings) {
  const out = [];

  const langSelections =
    settings.predefined_words?.language || {};

  Object.entries(langSelections).forEach(
    ([subKey, entry]) => {
      const ids =
        Array.isArray(entry?.selectedIds)
          ? entry.selectedIds
          : [];

      const libraryItems =
        wordLibrary.language[subKey]?.items || [];

      ids.forEach((id) => {
        const found =
          libraryItems.find(
            (item) =>
              item.id === id
          );

        if (found && found.word) {
          out.push(found.word);
        }
      });
    }
  );

  return out;
}

function ensurePredefinedSelection(
  settings,
  categoryKey,
  subKey,
  items
) {
  if (!settings.predefined_words) {
    settings.predefined_words = {};
  }

  if (!settings.predefined_words[categoryKey]) {
    settings.predefined_words[categoryKey] = {};
  }

  const defaultIds =
    Array.isArray(items)
      ? items.map((item) => item.id)
      : [];

  const existing =
    settings.predefined_words[categoryKey][subKey];

  if (
    !existing ||
    !Array.isArray(existing.selectedIds)
  ) {
    settings.predefined_words[categoryKey][subKey] = {
      selectedIds: [
        ...defaultIds,
      ],
    };
  }

  return settings.predefined_words[categoryKey][subKey];
}

function migrateNewLanguageWordDefaults(settings) {
  const safe =
    ensureFilterSettings(
      settings || {}
    );

  if (
    localStorage.getItem(
      LANGUAGE_WORDLIST_MIGRATION_KEY
    ) === 'done'
  ) {
    return {
      settings: safe,
      changed: false,
    };
  }

  let changed = false;

  Object.entries(
    LANGUAGE_WORDLIST_NEW_DEFAULT_IDS
  ).forEach(
    ([subKey, idsToAdd]) => {
      const items =
        Array.isArray(
          wordLibrary.language?.[subKey]?.items
        )
          ? wordLibrary.language[subKey].items
          : [];

      const validIds =
        new Set(
          items.map(
            (item) => item.id
          )
        );

      const selection =
        ensurePredefinedSelection(
          safe,
          'language',
          subKey,
          items
        );

      const selectedIds =
        new Set(
          Array.isArray(selection.selectedIds)
            ? selection.selectedIds
            : []
        );

      idsToAdd.forEach((id) => {
        if (
          validIds.has(id) &&
          !selectedIds.has(id)
        ) {
          selectedIds.add(id);
          changed = true;
        }
      });

      safe.predefined_words.language[subKey] = {
        selectedIds:
          Array.from(selectedIds),
      };
    }
  );

  return {
    settings: safe,
    changed,
  };
}

function mapFilterSensitivityToPreference(value) {
  const numeric =
    Number(value) || 0;

  if (numeric <= 1) {
    return 0.2;
  }

  if (numeric >= 3) {
    return 0.9;
  }

  return 0.7;
}

function mapPreferenceSensitivityToFilter(value) {
  if (typeof value !== 'number') {
    return 2;
  }

  if (value < 0.34) {
    return 1;
  }

  if (value < 0.67) {
    return 2;
  }

  return 3;
}

function filterSettingsToPreferences(filterSettings) {
  const safe =
    ensureFilterSettings(
      filterSettings || {}
    );

  const categories = {};

  Object.keys(FILTER_CATEGORY_CONFIG).forEach(
    (key) => {
      const actionSelectValue =
        safe.actions[key]?.action ||
        FILTER_CATEGORY_CONFIG[key].defaults.action;

      const action =
        mapSelectToAction(
          actionSelectValue,
          'mute'
        );

      const duration =
        Number(safe.actions[key]?.duration) ||
        ACTION_DEFAULT_DURATIONS[action] ||
        4;

      const sensitivity =
        mapFilterSensitivityToPreference(
          safe.actions[key]?.sensitivity
        );

      categories[key] = {
        enabled:
          !!safe.filters_enabled[key],
        action,
        duration,
        sensitivity,
      };
    }
  );

  Object.entries(
    wordLibrary.language || {}
  ).forEach(
    ([subKey, payload]) => {
      const words =
        Array.isArray(payload?.items)
          ? payload.items
          : Array.isArray(payload)
            ? payload
            : [];

      ensurePredefinedSelection(
        safe,
        'language',
        subKey,
        words
      );
    }
  );

  const customLanguageItems =
    Array.isArray(
      safe.custom_words.language
    )
      ? safe.custom_words.language
          .map((w) =>
            typeof w === 'string'
              ? w.trim()
              : ''
          )
          .filter(Boolean)
      : [];

  const predefinedItems =
    getSelectedPredefinedWords(safe);

  const blocklistItems =
    Array.from(
      new Set([
        ...predefinedItems,
        ...customLanguageItems,
      ])
    );

  categories.language = {
    ...categories.language,
    items: blocklistItems,
  };

  const languageDuration =
    Number(
      safe.actions.language?.duration
    ) || 4;

  return {
    enabled: true,
    categories,
    sensitivity: 0.7,
    blocklist: {
      enabled: true,
      mode: 'whole_word',
      action: 'mute',
      duration:
        languageDuration || 4,
      items:
        blocklistItems,
    },
  };
}

function preferencesToFilterSettings(
  prefs,
  existingFilterSettings = {}
) {
  const next =
    ensureFilterSettings(
      existingFilterSettings
    );

  const categories =
    (prefs && prefs.categories) || {};

  Object.entries(categories).forEach(
    ([key, cfg]) => {
      if (
        !FILTER_CATEGORY_CONFIG[key]
      ) {
        return;
      }

      next.filters_enabled[key] =
        cfg?.enabled ??
        next.filters_enabled[key];

      const mappedAction =
        mapActionToSelect(
          cfg?.action ||
          next.actions[key].action
        );

      next.actions[key] = {
        ...next.actions[key],
        action: mappedAction,
        duration:
          cfg?.duration ??
          next.actions[key].duration,
        sensitivity:
          mapPreferenceSensitivityToFilter(
            cfg?.sensitivity ??
            prefs?.sensitivity
          ),
      };
    }
  );

  const blocklistItems =
    Array.isArray(
      prefs?.blocklist?.items
    )
      ? prefs.blocklist.items
          .map((w) =>
            typeof w === 'string'
              ? w.trim()
              : ''
          )
          .filter(Boolean)
      : Array.isArray(
          prefs?.categories?.language?.items
        )
        ? prefs.categories.language.items
            .map((w) =>
              typeof w === 'string'
                ? w.trim()
                : ''
            )
            .filter(Boolean)
        : [];

  const hasExplicitLanguageSelection =
    Array.isArray(prefs?.blocklist?.items)
    || Array.isArray(prefs?.categories?.language?.items);

  const languageLists =
    wordLibrary.language || {};

  const wordToId = {};

  Object.entries(languageLists).forEach(
    ([subKey, payload]) => {
      const items =
        Array.isArray(payload?.items)
          ? payload.items
          : [];

      items.forEach((item) => {
        if (item.word) {
          wordToId[
            item.word.toLowerCase()
          ] = item.id;
        }
      });
    }
  );

  const matchedSubfilters = {};
  const remaining = [];

  blocklistItems.forEach((word) => {
    const key =
      word.toLowerCase();

    const id =
      wordToId[key];

    if (id) {
      Object.entries(languageLists).forEach(
        ([subKey, payload]) => {
          const items =
            Array.isArray(payload?.items)
              ? payload.items
              : [];

          if (
            items.some(
              (item) =>
                item.id === id
            )
          ) {
            const entry =
              matchedSubfilters[subKey] ||
              {
                selectedIds: [],
              };

            if (
              !entry.selectedIds.includes(id)
            ) {
              entry.selectedIds.push(id);
            }

            matchedSubfilters[subKey] =
              entry;
          }
        }
      );
    } else {
      remaining.push(word);
    }
  });

  Object.entries(languageLists).forEach(
    ([subKey, payload]) => {
      const items =
        Array.isArray(payload?.items)
          ? payload.items
          : [];

      const selection =
        matchedSubfilters[subKey];

      if (selection) {
        next.predefined_words.language[subKey] = {
          selectedIds:
            selection.selectedIds,
        };
      } else if (hasExplicitLanguageSelection) {
        // An explicit empty blocklist is an intentional user choice. Do not
        // turn it back into the library defaults during restore.
        next.predefined_words.language[subKey] = {
          selectedIds: [],
        };
      } else if (items.length) {
        next.predefined_words.language[subKey] = {
          selectedIds:
            items.map(
              (i) => i.id
            ),
        };
      }
    }
  );

  if (hasExplicitLanguageSelection) {
    next.custom_words.language = remaining;
  } else if (remaining.length) {
    next.custom_words.language =
      remaining;
  }

  return ensureFilterSettings(next);
}

const ACTION_DEFAULT_DURATIONS = {
  mute: 4,
  skip: 12,
  fast_forward: 8,
  none: 0,
};

function mapSelectToAction(
  value,
  fallback = 'mute'
) {
  switch (value) {
    case 'skip':
      return 'skip';

    case 'fast-forward':
      return 'fast_forward';

    case 'log-only':
      return 'none';

    case 'mute':
    default:
      return fallback;
  }
}

function mapActionToSelect(action) {
  if (action === 'fast_forward') {
    return 'fast-forward';
  }

  if (action === 'skip') {
    return 'skip';
  }

  if (action === 'none') {
    return 'log-only';
  }

  return 'mute';
}

function loadPreferencesFromCache() {
  try {
    const raw =
      localStorage.getItem(
        preferencesCacheKey
      );

    return raw
      ? JSON.parse(raw)
      : null;
  } catch (err) {
    console.error(
      '[ISWEEP] Failed to parse cached preferences',
      err
    );

    return null;
  }
}

function cachePreferences(prefs) {
  try {
    localStorage.setItem(
      preferencesCacheKey,
      JSON.stringify(prefs)
    );
  } catch (err) {
    console.error(
      '[ISWEEP] Failed to cache preferences',
      err
    );
  }
}

function preferencesToUi(prefs) {
  const categories =
    (prefs && prefs.categories) || {};

  const language =
    categories.language || {};

  const sexual =
    categories.sexual || {};

  const violence =
    categories.violence || {};

  const sensitivityNumeric =
    typeof prefs?.sensitivity === 'number'
      ? prefs.sensitivity
      : 0.7;

  const sliderValue =
    sensitivityNumeric < 0.34
      ? 1
      : sensitivityNumeric < 0.67
        ? 2
        : 3;

  return {
    filter_profanity:
      language.enabled ?? true,

    filter_sexual:
      sexual.enabled ?? true,

    filter_violence:
      violence.enabled ?? true,

    action_profanity:
      mapActionToSelect(
        language.action
      ),

    action_sexual:
      mapActionToSelect(
        sexual.action || 'skip'
      ),

    action_violence:
      mapActionToSelect(
        violence.action ||
        'fast_forward'
      ),

    sensitivity:
      sliderValue,
  };
}

function uiToPreferences(saved) {
  const sensitivityValue =
    Number(saved.sensitivity || 2);

  const numericSensitivity =
    sensitivityValue <= 1
      ? 0.2
      : sensitivityValue >= 3
        ? 0.9
        : 0.7;

  const languageAction =
    mapSelectToAction(
      saved.action_profanity || 'mute',
      'mute'
    );

  const sexualAction =
    mapSelectToAction(
      saved.action_sexual || 'skip',
      'skip'
    );

  const violenceAction =
    mapSelectToAction(
      saved.action_violence || 'skip',
      'fast_forward'
    );

  return {
    enabled: true,
    categories: {
      language: {
        enabled:
          !!saved.filter_profanity,
        action:
          languageAction,
        duration:
          ACTION_DEFAULT_DURATIONS[
            languageAction
          ] ?? 4,
      },

      sexual: {
        enabled:
          !!saved.filter_sexual,
        action:
          sexualAction,
        duration:
          ACTION_DEFAULT_DURATIONS[
            sexualAction
          ] ?? 12,
      },

      violence: {
        enabled:
          !!saved.filter_violence,
        action:
          violenceAction,
        duration:
          ACTION_DEFAULT_DURATIONS[
            violenceAction
          ] ?? 8,
      },
    },

    sensitivity:
      numericSensitivity,
  };
}

async function fetchPreferencesFromBackend() {
  const token =
    localStorage.getItem(
      tokenStorageKey
    );

  if (!token) {
    return null;
  }

  try {
    console.log(
      '[ISWEEP][FE] loading preferences...',
      getBackendUrl()
    );

    const res =
      await fetch(
        `${getBackendUrl()}/preferences`,
        {
          method: 'GET',
          headers: {
            Authorization:
              `Bearer ${token}`,
          },
        }
      );

    if (!res.ok) {
      const msg =
        await res.text();

      console.warn(
        '[ISWEEP][FE] /preferences failed',
        res.status,
        msg || ''
      );

      throw new Error(
        msg ||
        'Failed to load preferences'
      );
    }

    const prefs =
      await res.json();

    console.log(
      '[ISWEEP][FE] /preferences success',
      res.status
    );

    cachePreferences(prefs);

    return prefs;
  } catch (err) {
    console.warn(
      '[ISWEEP][FE] Failed to fetch preferences from backend',
      err
    );

    return null;
  }
}

async function persistPreferences(preferences) {
  const token =
    localStorage.getItem(
      tokenStorageKey
    );

  if (!token) {
    console.warn(
      '[ISWEEP][FE] missing auth token; saved locally'
    );

    throw new Error(
      'Missing auth token'
    );
  }

  console.log(
    '[ISWEEP][FE] saving preferences...',
    getBackendUrl()
  );

  const res =
    await fetch(
      `${getBackendUrl()}/preferences`,
      {
        method: 'PUT',
        headers: {
          'Content-Type':
            'application/json',
          Authorization:
            `Bearer ${token}`,
        },
        body:
          JSON.stringify(preferences),
      }
    );

  if (!res.ok) {
    const message =
      await res.text();

    console.warn(
      '[ISWEEP][FE] /preferences failed',
      res.status,
      message || ''
    );

    throw new Error(
      message ||
      'Failed to save preferences'
    );
  }

  const prefs =
    await res.json();

  console.log(
    '[ISWEEP][FE] /preferences success',
    res.status
  );

  cachePreferences(prefs);

  return {
    prefs,
    status:
      res.status,
  };
}

function setFilterSaveStatus(message, isError = false) {
  let status = document.getElementById('isweepFilterSyncStatus');
  if (!status) {
    const actions = document.querySelector('.filters-actions');
    if (!actions) return;
    status = document.createElement('div');
    status.id = 'isweepFilterSyncStatus';
    status.setAttribute('role', 'status');
    status.style.marginTop = '8px';
    status.style.fontSize = '0.9rem';
    status.style.width = '100%';
    actions.insertAdjacentElement('afterend', status);
  }
  status.textContent = message;
  status.style.color = isError ? '#b42318' : 'var(--muted)';
}

function getSavedLanguageWordCount(preferences) {
  if (Array.isArray(preferences?.blocklist?.items)) {
    return preferences.blocklist.items.length;
  }
  if (Array.isArray(preferences?.categories?.language?.items)) {
    return preferences.categories.language.items.length;
  }
  return 0;
}

async function fetchAndCachePreferences() {
  const prefs =
    await fetchPreferencesFromBackend();

  if (prefs) {
    saveSettingsToStorage(
      preferencesToUi(prefs)
    );
  }

  return prefs;
}

async function loadPreferencesUiState() {
  const backendPrefs =
    await fetchPreferencesFromBackend();

  if (backendPrefs) {
    saveSettingsToStorage(
      preferencesToUi(
        backendPrefs
      )
    );

    return preferencesToUi(
      backendPrefs
    );
  }

  const cachedPrefs =
    loadPreferencesFromCache();

  if (cachedPrefs) {
    console.log(
      '[ISWEEP][FE] falling back to cached preferences'
    );

    return preferencesToUi(
      cachedPrefs
    );
  }

  console.log(
    '[ISWEEP][FE] falling back to local settings storage'
  );

  return loadSettingsFromStorage();
}

//-----------------------------------------------------
//  FILTERS PAGE: CONTROL CENTER
//-----------------------------------------------------

document.addEventListener(
  'DOMContentLoaded',
  async () => {
    const filtersPage =
      document.querySelector(
        '[data-filters-page]'
      );

    if (!filtersPage) {
      return;
    }

    function decodeToken(token) {
      try {
        return atob(token);
      } catch (err) {
        return '';
      }
    }

    async function loadWordLibrary() {
      try {
        const res =
          await fetch(
            LANGUAGE_WORDLIST_URL
          );

        if (!res.ok) {
          return;
        }

        const data =
          await res.json();

        const language =
          data.language || {};

        const mapped = {};

        Object.entries(language).forEach(
          ([subKey, payload]) => {
            const rawItems =
              Array.isArray(
                payload?.items
              )
                ? payload.items
                : [];

            const normalized =
              rawItems
                .map(
                  (item, idx) => {
                    if (
                      typeof item ===
                      'string'
                    ) {
                      return {
                        id:
                          `${subKey}-${idx}`,
                        token:
                          item,
                        word:
                          decodeToken(
                            item
                          ),
                      };
                    }

                    return {
                      id:
                        item.id ||
                        `${subKey}-${idx}`,
                      token:
                        item.token ||
                        '',
                      word:
                        decodeToken(
                          item.token ||
                          ''
                        ),
                    };
                  }
                )
                .map(
                  (entry) => ({
                    ...entry,
                    maskedPreview:
                      maskWordPreservingNonLetters(
                        entry.word
                      ),
                  })
                );

            mapped[subKey] = {
              items:
                normalized,
            };
          }
        );

        wordLibrary.language =
          mapped;
      } catch (err) {
        console.warn(
          '[ISWEEP][FE] Failed to load word library',
          err
        );
      }
    }

    await loadWordLibrary();

    let settings =
      ensureFilterSettings(
        loadSettingsFromStorage()
      );

    const prefs =
      await fetchPreferencesFromBackend();

    if (prefs) {
      settings =
        preferencesToFilterSettings(
          prefs,
          settings
        );
    }

    const migration =
      migrateNewLanguageWordDefaults(
        settings
      );

    settings =
      migration.settings;

    saveSettingsToStorage(
      settings
    );

    if (prefs) {
      if (migration.changed) {
        try {
          await persistPreferences(
            filterSettingsToPreferences(
              settings
            )
          );

          localStorage.setItem(
            LANGUAGE_WORDLIST_MIGRATION_KEY,
            'done'
          );

          console.log(
            '[ISWEEP][FE] Added new default language words to saved preferences.'
          );
        } catch (error) {
          console.warn(
            '[ISWEEP][FE] New default language words saved locally; backend sync will retry when filters are saved.',
            error
          );
        }
      } else {
        localStorage.setItem(
          LANGUAGE_WORDLIST_MIGRATION_KEY,
          'done'
        );
      }
    }

    let currentCategory =
      'language';

    const tileButtons =
      filtersPage.querySelectorAll(
        '[data-filter-tile]'
      );

    const categoryName =
      filtersPage.querySelector(
        '[data-category-name]'
      );

    const categoryToggle =
      filtersPage.querySelector(
        '[data-category-toggle]'
      );

    const subcategoryList =
      filtersPage.querySelector(
        '[data-subcategory-list]'
      );

    const customWordInput =
      document.getElementById(
        'customWordInput'
      );

    const customWordAdd =
      document.getElementById(
        'customWordAdd'
      );

    const customWordAddInline =
      document.getElementById(
        'customWordAddInline'
      );

    const customWordList =
      document.getElementById(
        'customWordList'
      );

    const actionSelect =
      document.getElementById(
        'actionSelect'
      );

    const durationInput =
      document.getElementById(
        'actionDuration'
      );

    const sensitivityRange =
      document.getElementById(
        'sensitivityRange'
      );

    const sensitivityValue =
      document.getElementById(
        'sensitivityValue'
      );

    const saveButton =
      document.getElementById(
        'saveFilters'
      );

    const resetButton =
      document.getElementById(
        'resetCategory'
      );

    const cancelButton =
      document.getElementById(
        'cancelFilters'
      );

    function applyKidPreset() {
      Object.keys(
        settings.filters_enabled
      ).forEach(
        (categoryKey) => {
          settings.filters_enabled[
            categoryKey
          ] = true;

          if (
            settings.subfilters_enabled &&
            settings.subfilters_enabled[
              categoryKey
            ]
          ) {
            Object.keys(
              settings.subfilters_enabled[
                categoryKey
              ]
            ).forEach(
              (subKey) => {
                settings.subfilters_enabled[
                  categoryKey
                ][subKey] = true;
              }
            );
          }

          settings.actions[
            categoryKey
          ] = {
            action:
              categoryKey ===
              'language'
                ? 'mute'
                : 'skip',
            duration: 15,
            sensitivity: 5,
          };
        }
      );

      saveSettingsToStorage(
        settings
      );

      renderTiles();
      renderCategoryDetail();
    }

    const presetButtons =
      filtersPage.querySelectorAll(
        '.preset-buttons button'
      );

    presetButtons.forEach(
      (btn) => {
        const label =
          (
            btn.textContent ||
            ''
          ).trim();

        if (
          label ===
          'Kid Mode (Under 13)'
        ) {
          btn.addEventListener(
            'click',
            applyKidPreset
          );
        }
      }
    );

    function setCurrentCategory(next) {
      currentCategory =
        next;

      expandedSubfilterKey =
        null;

      renderTiles();
      renderCategoryDetail();
    }

    function renderTiles() {
      tileButtons.forEach(
        (button) => {
          const key =
            button.getAttribute(
              'data-filter-tile'
            );

          const isSelected =
            key ===
            currentCategory;

          const isEnabled =
            !!settings.filters_enabled[
              key
            ];

          button.classList.toggle(
            'tile-selected',
            isSelected
          );

          const indicator =
            button.querySelector(
              '.enabled-dot'
            );

          if (indicator) {
            indicator.classList.toggle(
              'enabled-on',
              isEnabled
            );
          }
        }
      );
    }

    function renderSubcategories() {
      if (!subcategoryList) {
        return;
      }

      subcategoryList.innerHTML =
        '';

      const customWrap =
        document.getElementById(
          'customWordsSection'
        );

      if (customWrap) {
        customWrap.style.display =
          currentCategory ===
          'language'
            ? 'block'
            : 'none';
      }

      const config =
        FILTER_CATEGORY_CONFIG[
          currentCategory
        ];

      config.subcategories.forEach(
        (sub) => {
          const row =
            document.createElement(
              'div'
            );

          row.className =
            'sub-row';

          const left =
            document.createElement(
              'label'
            );

          left.className =
            'sub-row-left';

          const checkbox =
            document.createElement(
              'input'
            );

          checkbox.type =
            'checkbox';

          checkbox.checked =
            !!settings.subfilters_enabled[
              currentCategory
            ][sub.key];

          checkbox.setAttribute(
            'data-subfilter',
            sub.key
          );

          const dot =
            document.createElement(
              'span'
            );

          dot.className =
            'enabled-dot';

          dot.classList.toggle(
            'enabled-on',
            checkbox.checked
          );

          const name =
            document.createElement(
              'span'
            );

          name.textContent =
            sub.label;

          left.appendChild(
            checkbox
          );

          left.appendChild(
            dot
          );

          left.appendChild(
            name
          );

          const right =
            document.createElement(
              'div'
            );

          right.className =
            'sub-row-right';

          const badge =
            document.createElement(
              'span'
            );

          badge.className =
            'count-badge';

          const libraryEntry =
            wordLibrary[
              currentCategory
            ]?.[sub.key];

          const items =
            Array.isArray(
              libraryEntry?.items
            )
              ? libraryEntry.items
              : [];

          if (
            currentCategory ===
              'language' &&
            items.length
          ) {
            const selection =
              ensurePredefinedSelection(
                settings,
                'language',
                sub.key,
                items
              );

            const selectedIds =
              Array.isArray(
                selection.selectedIds
              )
                ? selection.selectedIds
                : [];

            badge.textContent =
              `${selectedIds.length}/${items.length}`;
          } else {
            badge.textContent =
              sub.count;
          }

          const chevron =
            document.createElement(
              'span'
            );

          chevron.className =
            'chevron';

          chevron.textContent =
            '›';

          chevron.classList.toggle(
            'open',
            expandedSubfilterKey ===
              sub.key
          );

          right.appendChild(
            badge
          );

          right.appendChild(
            chevron
          );

          row.appendChild(
            left
          );

          row.appendChild(
            right
          );

          function toggleWordPanel(event) {
            if (
              event.target instanceof
              HTMLInputElement
            ) {
              return;
            }

            if (
              currentCategory !==
              'language'
            ) {
              return;
            }

            if (
              expandedSubfilterKey ===
              sub.key
            ) {
              expandedSubfilterKey =
                null;
            } else {
              expandedSubfilterKey =
                sub.key;
            }

            renderSubcategories();
          }

          row.addEventListener(
            'click',
            toggleWordPanel
          );

  row.addEventListener(
  'change',
  (event) => {
    const target = event.target;

    if (!(target instanceof HTMLInputElement)) {
      return;
    }

    const key = target.getAttribute('data-subfilter');

    if (!key) {
      return;
    }

    // Turn the subcategory itself on/off.
    settings.subfilters_enabled[currentCategory][key] =
      target.checked;

    /*
     * LANGUAGE MASTER CHECKBOX
     *
     * Checking Profanity / Blasphemy / Childish / Slurs
     * automatically selects every predefined word inside it.
     *
     * Unchecking the category clears every predefined word
     * inside it.
     */
    if (currentCategory === 'language') {
      const libraryItems =
        Array.isArray(wordLibrary.language?.[key]?.items)
          ? wordLibrary.language[key].items
          : [];

      if (!settings.predefined_words) {
        settings.predefined_words = {};
      }

      if (!settings.predefined_words.language) {
        settings.predefined_words.language = {};
      }

      settings.predefined_words.language[key] = {
        selectedIds: target.checked
          ? libraryItems.map((item) => item.id)
          : [],
      };
    }

    dot.classList.toggle(
      'enabled-on',
      target.checked
    );

    // Save the selection locally immediately.
    saveSettingsToStorage(settings);

    /*
     * Re-render so the count and individual checkboxes
     * immediately show the new state.
     *
     * Example:
     * Profanity 0/33 -> 33/33
     */
    renderSubcategories();
    renderTiles();
  }
);
          subcategoryList.appendChild(
            row
          );

          if (
            expandedSubfilterKey ===
            sub.key
          ) {
            const panel =
              document.createElement(
                'div'
              );

            panel.className =
              'word-panel';

            const helper =
              document.createElement(
                'p'
              );

            helper.className =
              'muted mask-hint';

            helper.textContent =
              'Words are partially masked for clarity.';

            panel.appendChild(
              helper
            );

            const itemsForSub =
              items;

            if (
              !itemsForSub.length
            ) {
              const empty =
                document.createElement(
                  'p'
                );

              empty.className =
                'empty-hint';

              empty.textContent =
                'No predefined items for this subfilter.';

              panel.appendChild(
                empty
              );
            } else {
              const selection =
                ensurePredefinedSelection(
                  settings,
                  'language',
                  sub.key,
                  itemsForSub
                );

              const selectedIds =
                new Set(
                  selection.selectedIds ||
                  []
                );

              itemsForSub.forEach(
                (item) => {
                  const rowEl =
                    document.createElement(
                      'div'
                    );

                  rowEl.className =
                    'sub-row word-row';

                  const label =
                    document.createElement(
                      'label'
                    );

                  label.className =
                    'sub-row-left';

                  const wordCheckbox =
                    document.createElement(
                      'input'
                    );

                  wordCheckbox.type =
                    'checkbox';

                  wordCheckbox.checked =
                    selectedIds.has(
                      item.id
                    );

                  wordCheckbox.setAttribute(
                    'data-word-id',
                    item.id
                  );

                  const masked =
                    document.createElement(
                      'span'
                    );

                  masked.textContent =
                    item.maskedPreview;

                  label.appendChild(
                    wordCheckbox
                  );

                  label.appendChild(
                    masked
                  );

                  rowEl.appendChild(
                    label
                  );

                  wordCheckbox.addEventListener(
                    'change',
                    () => {
                      if (
                        wordCheckbox.checked
                      ) {
                        selectedIds.add(
                          item.id
                        );
                      } else {
                        selectedIds.delete(
                          item.id
                        );
                      }

                      settings.predefined_words.language[
                        sub.key
                      ] = {
                        selectedIds:
                          Array.from(
                            selectedIds
                          ),
                      };

                      renderSubcategories();
                    }
                  );

                  panel.appendChild(
                    rowEl
                  );
                }
              );
            }

            if (
              currentCategory ===
              'language'
            ) {
              const customSection =
                document.createElement(
                  'div'
                );

              customSection.className =
                'custom-words-inline';

              const heading =
                document.createElement(
                  'p'
                );

              heading.className =
                'eyebrow';

              heading.textContent =
                'Manage Custom Words';

              customSection.appendChild(
                heading
              );

              if (customWrap) {
                customWrap.style.marginTop =
                  '8px';

                customWrap.style.borderTop =
                  '1px solid var(--border)';

                customWrap.style.paddingTop =
                  '8px';

                customSection.appendChild(
                  customWrap
                );
              }

              panel.appendChild(
                customSection
              );
            }

            subcategoryList.appendChild(
              panel
            );
          }
        }
      );

      if (
        currentCategory ===
          'language' &&
        !expandedSubfilterKey &&
        customWrap
      ) {
        subcategoryList.insertAdjacentElement(
          'afterend',
          customWrap
        );
      }
    }

    function renderCustomWords() {
      if (!customWordList) {
        return;
      }

      customWordList.innerHTML =
        '';

      const words =
        settings.custom_words[
          currentCategory
        ] || [];

      if (!words.length) {
        const empty =
          document.createElement(
            'p'
          );

        empty.className =
          'empty-hint';

        empty.textContent =
          'No custom words yet.';

        customWordList.appendChild(
          empty
        );

        return;
      }

      words.forEach(
        (word) => {
          const chip =
            document.createElement(
              'span'
            );

          chip.className =
            'word-chip';

          chip.textContent =
            word;

          const remove =
            document.createElement(
              'button'
            );

          remove.type =
            'button';

          remove.className =
            'chip-remove';

          remove.textContent =
            '×';

          remove.addEventListener(
            'click',
            () => {
              settings.custom_words[
                currentCategory
              ] =
                words.filter(
                  (w) =>
                    w !== word
                );

              renderCustomWords();
            }
          );

          chip.appendChild(
            remove
          );

          customWordList.appendChild(
            chip
          );
        }
      );
    }

    function renderCategoryDetail() {
      const config =
        FILTER_CATEGORY_CONFIG[
          currentCategory
        ];

      if (categoryName) {
        categoryName.textContent =
          `${config.icon} ${config.label}`;
      }

      if (categoryToggle) {
        categoryToggle.checked =
          !!settings.filters_enabled[
            currentCategory
          ];
      }

      renderSubcategories();
      renderCustomWords();

      if (actionSelect) {
        actionSelect.value =
          settings.actions[
            currentCategory
          ].action;
      }

      if (durationInput) {
        durationInput.value =
          settings.actions[
            currentCategory
          ].duration;
      }

      if (sensitivityRange) {
        sensitivityRange.value =
          settings.actions[
            currentCategory
          ].sensitivity;

        if (sensitivityValue) {
          sensitivityValue.textContent =
            settings.actions[
              currentCategory
            ].sensitivity;
        }
      }
    }

    function addCustomWord() {
      if (!customWordInput) {
        return;
      }

      const value =
        customWordInput.value.trim();

      if (!value) {
        return;
      }

      const words =
        settings.custom_words[
          currentCategory
        ] || [];

      if (
        !words.includes(value)
      ) {
        settings.custom_words[
          currentCategory
        ] = [
          ...words,
          value,
        ];

        renderCustomWords();

        customWordInput.value =
          '';

        saveSettingsToStorage(
          settings
        );
      }
    }

    tileButtons.forEach(
      (button) => {
        button.addEventListener(
          'click',
          () => {
            const key =
              button.getAttribute(
                'data-filter-tile'
              );

            if (key) {
              setCurrentCategory(
                key
              );
            }
          }
        );
      }
    );

    if (categoryToggle) {
      categoryToggle.addEventListener(
        'change',
        (event) => {
          const target =
            event.target;

          if (
            !(
              target instanceof
              HTMLInputElement
            )
          ) {
            return;
          }

          settings.filters_enabled[
            currentCategory
          ] =
            target.checked;

          renderTiles();
        }
      );
    }

    if (actionSelect) {
      actionSelect.addEventListener(
        'change',
        () => {
          settings.actions[
            currentCategory
          ].action =
            actionSelect.value;
        }
      );
    }

    if (durationInput) {
      durationInput.addEventListener(
        'change',
        () => {
          const next =
            Number(
              durationInput.value
            ) || 0;

          settings.actions[
            currentCategory
          ].duration =
            Math.max(
              0,
              next
            );
        }
      );
    }

    if (sensitivityRange) {
      sensitivityRange.addEventListener(
        'input',
        () => {
          const next =
            Number(
              sensitivityRange.value
            ) || 1;

          settings.actions[
            currentCategory
          ].sensitivity =
            next;

          if (
            sensitivityValue
          ) {
            sensitivityValue.textContent =
              next;
          }
        }
      );
    }

    if (customWordInput) {
      const wireAdd =
        (button) => {
          if (button) {
            button.addEventListener(
              'click',
              addCustomWord
            );
          }
        };

      wireAdd(customWordAdd);
      wireAdd(customWordAddInline);

      customWordInput.addEventListener(
        'keypress',
        (event) => {
          if (
            event.key ===
            'Enter'
          ) {
            event.preventDefault();
            addCustomWord();
          }
        }
      );
    }

    if (resetButton) {
      resetButton.addEventListener(
        'click',
        () => {
          const defaults =
            getDefaultFilterState();

          settings.filters_enabled[
            currentCategory
          ] =
            defaults.filters_enabled[
              currentCategory
            ];

          settings.subfilters_enabled[
            currentCategory
          ] = {
            ...defaults.subfilters_enabled[
              currentCategory
            ],
          };

          settings.actions[
            currentCategory
          ] = {
            ...defaults.actions[
              currentCategory
            ],
          };

          settings.custom_words[
            currentCategory
          ] = [
            ...(
              defaults.custom_words[
                currentCategory
              ] || []
            ),
          ];

          if (
            currentCategory ===
            'language'
          ) {
            Object.entries(
              wordLibrary.language ||
              {}
            ).forEach(
              ([subKey, payload]) => {
                const words =
                  Array.isArray(
                    payload?.items
                  )
                    ? payload.items
                    : Array.isArray(
                        payload
                      )
                      ? payload
                      : [];

                ensurePredefinedSelection(
                  settings,
                  'language',
                  subKey,
                  words
                );
              }
            );
          }

          renderCategoryDetail();
          renderTiles();
        }
      );
    }

    if (cancelButton) {
      cancelButton.addEventListener(
        'click',
        () => {
          settings =
            ensureFilterSettings(
              loadSettingsFromStorage()
            );

          renderTiles();
          renderCategoryDetail();
        }
      );
    }

    if (saveButton) {
      saveButton.addEventListener(
        'click',
        async () => {
          saveSettingsToStorage(
            settings
          );

          try {
            const prefsPayload =
              filterSettingsToPreferences(
                settings
              );

            const saveResult = await persistPreferences(
              prefsPayload
            );

            setFilterSaveStatus(
              `Saved to ISweep account/backend — ${getSavedLanguageWordCount(saveResult.prefs)} selected language words.`
            );

            localStorage.setItem(
              LANGUAGE_WORDLIST_MIGRATION_KEY,
              'done'
            );
          } catch (error) {
            console.warn(
              '[ISWEEP][FE] Failed to persist filters to backend; kept local copy',
              error
            );
            setFilterSaveStatus(
              `Saved locally only — backend sync failed: ${error.message || error}`,
              true
            );
          }
        }
      );
    }

    renderTiles();
    renderCategoryDetail();
  }
);

//-----------------------------------------------------
//  INDEX & HELP PAGE DEMO
//-----------------------------------------------------

// Demo wiring removed because the subtitle test and broom overlay were stripped
// from the homepage to keep it marketing-only with a single hero video.

//-----------------------------------------------------
//  HELP PAGE: CONTACT FORM
//-----------------------------------------------------

document.addEventListener(
  "DOMContentLoaded",
  () => {
    const contactForm =
      document.querySelector(
        "#contact-form .profile-form"
      );

    if (contactForm) {
      contactForm.addEventListener(
        "submit",
        (e) => {
          e.preventDefault();

          const name =
            contactForm.elements[
              "name"
            ].value;

          const email =
            contactForm.elements[
              "email"
            ].value;

          const topic =
            contactForm.elements[
              "topic"
            ].value;

          const message =
            contactForm.elements[
              "message"
            ].value;

          alert(
            `Thank you, ${name}! Your message about "${topic}" has been received. We'll respond to ${email} within 24 hours.`
          );

          contactForm.reset();
        }
      );
    }
  }
);

//-----------------------------------------------------
//  HELP PAGE: CHAT WIDGET
//-----------------------------------------------------

document.addEventListener(
  "DOMContentLoaded",
  () => {
    const chatToggle =
      document.getElementById(
        "chatToggle"
      );

    const chatWidget =
      document.getElementById(
        "chatWidget"
      );

    const chatClose =
      document.getElementById(
        "chatClose"
      );

    const chatForm =
      document.getElementById(
        "chatForm"
      );

    const chatInput =
      document.getElementById(
        "chatInput"
      );

    const chatLog =
      document.getElementById(
        "chatLog"
      );

    if (
      chatToggle &&
      chatWidget &&
      chatClose &&
      chatForm
    ) {
      chatToggle.addEventListener(
        "click",
        () => {
          chatWidget.classList.toggle(
            "open"
          );
        }
      );

      chatClose.addEventListener(
        "click",
        () => {
          chatWidget.classList.remove(
            "open"
          );
        }
      );

      chatForm.addEventListener(
        "submit",
        (event) => {
          event.preventDefault();

          const text =
            chatInput.value.trim();

          if (!text) {
            return;
          }

          const msg =
            document.createElement(
              "p"
            );

          msg.className =
            "chat-message user";

          msg.textContent =
            text;

          chatLog.appendChild(
            msg
          );

          chatInput.value =
            "";

          const reply =
            document.createElement(
              "p"
            );

          reply.className =
            "chat-message bot";

          reply.textContent =
            "Thanks for your message! In a real app, this would send to support.";

          chatLog.appendChild(
            reply
          );

          chatLog.scrollTop =
            chatLog.scrollHeight;
        }
      );
    }
  }
);
