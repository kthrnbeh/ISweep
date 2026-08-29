/*
 * ISWEEP COMPONENT: Website authentication/sync bridge.
 *
 * Purpose:
 * - Preserve the rich Filters-page state when a user signs in.
 * - Store the same backend token keys used by the extension and DVD workflow.
 * - Avoid the older login flow immediately replacing local Filters settings
 *   with a legacy backend preference object.
 * - Make it obvious on Filter.html whether changes can sync to the backend.
 *
 * This is intentionally small and additive while the shared-preference
 * architecture is being stabilized. Once verified, the logic can be folded
 * back into main.js.
 */
(function () {
  'use strict';

  const BACKEND_DEFAULT = 'http://127.0.0.1:5000';
  const BACKEND_URL_KEY = 'isweep-backend-url';
  const TOKEN_KEY = 'isweep-token';
  const SHARED_TOKEN_KEY = 'isweep_auth_token';
  const USER_ID_KEY = 'isweep-user-id';
  const AUTH_STATE_KEY = 'auth-state';

  function backendUrl() {
    return localStorage.getItem(BACKEND_URL_KEY) || BACKEND_DEFAULT;
  }

  function deriveInitials(name, email) {
    const source = name || email || '';
    const parts = source.split(/[^A-Za-z0-9]+/).filter(Boolean);
    if (!parts.length) return 'KB';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }

  function saveSession(result, email, name) {
    const token = result && result.token;
    const userId = result && result.user_id;

    if (!token || userId === undefined || userId === null) {
      throw new Error('Login response did not include a token and user id.');
    }

    const resolvedName = name || email.split('@')[0] || 'User';

    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(SHARED_TOKEN_KEY, token);
    localStorage.setItem(USER_ID_KEY, String(userId));
    localStorage.setItem(
      AUTH_STATE_KEY,
      JSON.stringify({
        name: resolvedName,
        email,
        token,
        initials: deriveInitials(resolvedName, email),
      })
    );
  }

  async function postAuth(path, payload) {
    const response = await fetch(`${backendUrl()}/auth/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Authentication failed (${response.status})`);
    }

    return response.json();
  }

  function closeModal() {
    const modal = document.getElementById('authModal');
    if (modal) modal.style.display = 'none';
  }

  function refreshAccountDisplay(email, name) {
    const resolvedName = name || email.split('@')[0] || 'User';
    document.querySelectorAll('.kb-avatar').forEach((avatar) => {
      avatar.textContent = deriveInitials(resolvedName, email);
    });

    const summary = document.getElementById('accountSummary');
    if (summary) summary.textContent = `${resolvedName}, ${email}`;
  }

  async function handleSignIn(form, event) {
    event.preventDefault();
    event.stopImmediatePropagation();

    const data = new FormData(form);
    const email = String(data.get('email') || '').trim();
    const password = String(data.get('password') || '');

    if (!email || !password) return;

    try {
      const result = await postAuth('login', { email, password });
      saveSession(result, email);
      refreshAccountDisplay(email);
      closeModal();

      alert(
        'Signed in to ISweep. Your existing Filters-page selections were preserved. Go to Filters and press Save to sync them to your account and ISweep DVD.'
      );
    } catch (error) {
      console.error('[ISWEEP][AUTH-SYNC] Login failed', error);
      alert('Login failed. Please check your email/password and make sure the local ISweep backend is running.');
    }
  }

  async function handleCreateAccount(form, event) {
    event.preventDefault();
    event.stopImmediatePropagation();

    const data = new FormData(form);
    const name = String(data.get('name') || '').trim();
    const email = String(data.get('email') || '').trim();
    const password = String(data.get('password') || '');
    const confirm = String(data.get('confirm') || '');

    if (password !== confirm) {
      alert('Passwords do not match.');
      return;
    }

    try {
      const result = await postAuth('signup', { name, email, password, confirm });
      saveSession(result, email, name);
      refreshAccountDisplay(email, name);
      closeModal();

      alert(
        'Account created and signed in. Go to Filters and press Save to sync your current selections to the account and ISweep DVD.'
      );
    } catch (error) {
      console.error('[ISWEEP][AUTH-SYNC] Signup failed', error);
      alert('Signup failed. Please make sure the local ISweep backend is running and try again.');
    }
  }

  function addFilterSyncStatus() {
    const filtersPage = document.querySelector('[data-filters-page]');
    if (!filtersPage) return;

    const token = localStorage.getItem(TOKEN_KEY);
    const account = (() => {
      try {
        return JSON.parse(localStorage.getItem(AUTH_STATE_KEY) || 'null');
      } catch (_) {
        return null;
      }
    })();

    const banner = document.createElement('div');
    banner.id = 'isweepSyncStatus';
    banner.className = 'card';
    banner.style.marginBottom = '14px';
    banner.style.padding = '10px 14px';
    banner.style.display = 'flex';
    banner.style.alignItems = 'center';
    banner.style.justifyContent = 'space-between';
    banner.style.gap = '12px';

    const text = document.createElement('span');

    if (token) {
      text.textContent = `Signed in${account?.email ? ` as ${account.email}` : ''}. Press Save to sync these filters with the backend, extension, and ISweep DVD.`;
      banner.appendChild(text);
    } else {
      text.textContent = 'Not signed in. Filter changes are currently stored only in this browser and cannot reach ISweep DVD.';
      banner.appendChild(text);

      const link = document.createElement('a');
      link.href = 'Account.html';
      link.textContent = 'Sign in';
      link.className = 'btn btn-primary';
      link.style.whiteSpace = 'nowrap';
      banner.appendChild(link);
    }

    filtersPage.insertBefore(banner, filtersPage.firstChild);
  }

  // Capture submit before main.js's bubble-phase handlers. This prevents the
  // legacy login flow from immediately overwriting the richer local filter state.
  document.addEventListener(
    'submit',
    (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;

      if (form.id === 'signInForm') {
        handleSignIn(form, event);
      } else if (form.id === 'createAccountForm') {
        handleCreateAccount(form, event);
      }
    },
    true
  );

  // main.js historically did not clear the shared extension token on logout.
  document.addEventListener(
    'click',
    (event) => {
      const target = event.target instanceof Element
        ? event.target.closest('[data-logout]')
        : null;
      if (target) localStorage.removeItem(SHARED_TOKEN_KEY);
    },
    true
  );

  document.addEventListener('DOMContentLoaded', addFilterSyncStatus);
})();
