"""
ISweep DVD - Shared Preference Bridge

Connects ISweep DVD to the existing ISweep preference format used by:

    Filter.html
        ↓
    main.js
        ↓
    ISweep Backend
        ↓
    /preferences

ISweep DVD does NOT maintain a separate preference system.

The same account preferences used by the browser extension are
loaded and translated into the current DVD Decision Engine model.

Version 1 currently uses the language blocklist because the DVD
Decision Engine presently understands text ALLOW/MUTE decisions.

Future versions will also consume:
- intimacy
- violence
- substances
- horror
- sensitivity
- skip
- fast_forward
- category-specific AI decisions
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from dvd.decision_engine import UserPreferences


DEFAULT_BACKEND_URL = "http://127.0.0.1:5000"


class PreferencesError(Exception):
    """
    Raised when ISweep DVD cannot authenticate with or retrieve
    preferences from the ISweep backend.
    """


@dataclass
class BackendSession:
    """
    Represents an authenticated ISweep backend session.
    """

    token: str
    user_id: int | None = None


class ISweepPreferencesClient:
    """
    Small HTTP client used by ISweep DVD.

    It communicates with the SAME backend already used by the
    ISweep website and Chrome extension.
    """

    def __init__(self, backend_url: str = DEFAULT_BACKEND_URL):
        self.backend_url = backend_url.rstrip("/")

    def health_check(self) -> bool:
        """
        Check whether the local ISweep backend is running.
        """

        url = f"{self.backend_url}/health"

        try:
            req = request.Request(
                url,
                method="GET",
            )

            with request.urlopen(req, timeout=3) as response:
                return 200 <= response.status < 300

        except (error.URLError, TimeoutError):
            return False

    def login(
        self,
        email: str,
        password: str,
    ) -> BackendSession:
        """
        Sign in through the existing ISweep /auth/login endpoint.

        The password is sent only to the local ISweep backend and
        is not stored by this class.
        """

        payload = {
            "email": email.strip(),
            "password": password,
        }

        response = self._json_request(
            path="/auth/login",
            method="POST",
            payload=payload,
        )

        token = str(response.get("token") or "").strip()

        if not token:
            raise PreferencesError(
                "ISweep login succeeded but no authentication token "
                "was returned."
            )

        user_id = response.get("user_id")

        try:
            normalized_user_id = int(user_id)
        except (TypeError, ValueError):
            normalized_user_id = None

        return BackendSession(
            token=token,
            user_id=normalized_user_id,
        )

    def get_preferences(
        self,
        session: BackendSession,
    ) -> dict[str, Any]:
        """
        Retrieve the user's saved ISweep preferences.

        This calls the same authenticated GET /preferences endpoint
        used by the existing ISweep frontend.
        """

        if not session.token:
            raise PreferencesError(
                "An authentication token is required."
            )

        response = self._json_request(
            path="/preferences",
            method="GET",
            token=session.token,
        )

        if not isinstance(response, dict):
            raise PreferencesError(
                "ISweep returned an invalid preference response."
            )

        return response

    def _json_request(
        self,
        path: str,
        method: str,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a JSON HTTP request to the ISweep backend.
        """

        url = f"{self.backend_url}{path}"

        body = None

        headers = {
            "Accept": "application/json",
        }

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with request.urlopen(req, timeout=5) as response:
                raw = response.read().decode("utf-8")

        except error.HTTPError as exc:
            try:
                message = exc.read().decode("utf-8")
            except Exception:
                message = ""

            if exc.code == 401:
                raise PreferencesError(
                    "ISweep rejected the login or authentication token."
                ) from exc

            raise PreferencesError(
                f"ISweep backend returned HTTP {exc.code}: "
                f"{message or exc.reason}"
            ) from exc

        except error.URLError as exc:
            raise PreferencesError(
                "Could not connect to the ISweep backend at "
                f"{self.backend_url}."
            ) from exc

        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise PreferencesError(
                "ISweep backend returned invalid JSON."
            ) from exc

        if not isinstance(parsed, dict):
            raise PreferencesError(
                "ISweep backend returned an unexpected response."
            )

        return parsed


def _clean_word_list(values: Any) -> list[str]:
    """
    Normalize a list of words/phrases while preserving order.

    Matching itself remains case-insensitive inside the Decision Engine.
    """

    if not isinstance(values, list):
        return []

    output: list[str] = []
    seen: set[str] = set()

    for raw_value in values:
        if not isinstance(raw_value, str):
            continue

        value = raw_value.strip()

        if not value:
            continue

        comparison = value.casefold()

        if comparison in seen:
            continue

        seen.add(comparison)
        output.append(value)

    return output


def extract_language_blocklist(
    preferences: dict[str, Any],
) -> list[str]:
    """
    Extract language words from the current ISweep website schema.

    Current preferred location:

        preferences["blocklist"]["items"]

    Compatible fallback:

        preferences["categories"]["language"]["items"]

    Keeping both allows ISweep DVD to remain compatible with current
    and transitional ISweep preference payloads.
    """

    if not isinstance(preferences, dict):
        return []

    if preferences.get("enabled") is False:
        return []

    blocklist = preferences.get("blocklist")

    if isinstance(blocklist, dict):
        if blocklist.get("enabled") is not False:
            items = _clean_word_list(blocklist.get("items"))

            if items:
                return items

    categories = preferences.get("categories")

    if not isinstance(categories, dict):
        return []

    language = categories.get("language")

    if not isinstance(language, dict):
        return []

    return _clean_word_list(language.get("items"))


def preferences_to_decision_preferences(
    preferences: dict[str, Any],
) -> UserPreferences:
    """
    Translate the full ISweep website preference object into the
    subset currently understood by Decision Engine v1.

    Later versions will expand UserPreferences instead of changing
    the website preference format.
    """

    mute_words = extract_language_blocklist(preferences)

    return UserPreferences(
        custom_mute_words=mute_words,
    )