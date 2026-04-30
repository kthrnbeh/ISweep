const SETTINGS_KEY = 'isweep-settings';

function loadSettingsFromStorage() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (err) {
    console.warn('[ISWEEP][SETTINGS] failed to parse local settings', err);
    return {};
  }
}

function saveSettingsToStorage(settings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

document.addEventListener('DOMContentLoaded', () => {
  const notificationsForm = document.getElementById('notificationsForm');
  const parentalForm = document.getElementById('parentalForm');

  if (!notificationsForm && !parentalForm) return;

  console.log('[ISWEEP][SETTINGS] filter controls moved to Filters page');

  const saved = loadSettingsFromStorage();

  if (notificationsForm) {
    notificationsForm.elements['notify-email'].checked = saved.notify_email ?? true;
    notificationsForm.elements['notify-inapp'].checked = saved.notify_inapp ?? true;
    notificationsForm.elements['notify-none'].checked = saved.notify_none ?? false;

    notificationsForm.addEventListener('submit', (e) => {
      e.preventDefault();
      saved.notify_email = notificationsForm.elements['notify-email'].checked;
      saved.notify_inapp = notificationsForm.elements['notify-inapp'].checked;
      saved.notify_none = notificationsForm.elements['notify-none'].checked;
      saveSettingsToStorage(saved);
      alert('Notification preferences saved.');
    });
  }

  if (parentalForm) {
    const pinInput = parentalForm.elements['parent-pin'];
    const requirePinCheckbox = parentalForm.elements['require-pin'];

    if (saved.parent_pin) {
      pinInput.value = saved.parent_pin;
    }
    requirePinCheckbox.checked = saved.require_pin ?? true;

    parentalForm.addEventListener('submit', (e) => {
      e.preventDefault();
      saved.parent_pin = pinInput.value;
      saved.require_pin = requirePinCheckbox.checked;
      saveSettingsToStorage(saved);
      alert('Parental PIN saved locally. (In a real app, this would be stored securely on the server.)');
    });
  }
});
