"""
ISweep DVD - Infrared Remote Controller

First physical hardware adapter for ISweep DVD.

The initial implementation targets BroadLink RM-series IR blasters
(such as the RM4 mini) through the optional ``broadlink`` Python
package. The rest of ISweep does not import that dependency directly,
so the existing website, extension, backend, Decision Engine, and
simulated remote remain independent from this hardware experiment.

The controller learns the user's existing remote-control buttons and
stores the captured IR packets locally. ISweep then re-sends those
same packets when it needs to press MUTE, PLAY, PAUSE, FAST FORWARD,
or SKIP.

No DVD/movie content is modified.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dvd.control.commands import RemoteCommand
from dvd.decision_engine import Action, Decision


DEFAULT_CODE_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "ir_codes.json"
)


class InfraredError(RuntimeError):
    """Raised when the physical infrared controller cannot operate."""


class IRCodeStore:
    """Persist learned IR packets without mixing them into app settings."""

    def __init__(self, path: str | Path = DEFAULT_CODE_PATH):
        self.path = Path(path)
        self.data: dict[str, Any] = {
            "version": 1,
            "devices": {},
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return

        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InfraredError(
                f"Could not read IR code file: {self.path}"
            ) from exc

        if not isinstance(parsed, dict):
            raise InfraredError("IR code file has an invalid format.")

        devices = parsed.get("devices")
        if not isinstance(devices, dict):
            devices = {}

        self.data = {
            "version": 1,
            "devices": devices,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _target_name(target: str) -> str:
        value = str(target).strip().lower()
        if not value:
            raise InfraredError("IR target name cannot be empty.")
        return value

    @staticmethod
    def _command_name(command: RemoteCommand | str) -> str:
        if isinstance(command, RemoteCommand):
            return command.value
        value = str(command).strip().upper()
        if not value:
            raise InfraredError("IR command name cannot be empty.")
        return value

    def set_code(
        self,
        target: str,
        command: RemoteCommand | str,
        packet: bytes,
    ) -> None:
        if not packet:
            raise InfraredError("Cannot save an empty IR packet.")

        target_name = self._target_name(target)
        command_name = self._command_name(command)
        devices = self.data.setdefault("devices", {})
        target_codes = devices.setdefault(target_name, {})
        target_codes[command_name] = packet.hex()
        self.save()

    def get_code(
        self,
        target: str,
        command: RemoteCommand | str,
    ) -> bytes | None:
        target_name = self._target_name(target)
        command_name = self._command_name(command)

        raw = (
            self.data.get("devices", {})
            .get(target_name, {})
            .get(command_name)
        )

        if not isinstance(raw, str) or not raw:
            return None

        try:
            return bytes.fromhex(raw)
        except ValueError as exc:
            raise InfraredError(
                f"Stored IR code for {target_name}/{command_name} is invalid."
            ) from exc

    def has_code(
        self,
        target: str,
        command: RemoteCommand | str,
    ) -> bool:
        return self.get_code(target, command) is not None


class BroadLinkInfraredRemote:
    """
    Physical IR remote implemented with a BroadLink RM-series blaster.

    A fake ``device`` can be injected during tests, so importing this module
    does not require the BroadLink dependency unless real hardware is used.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        device: Any | None = None,
        code_store: IRCodeStore | None = None,
        discovery_timeout: float = 5.0,
        tv_target: str = "tv",
        dvd_target: str = "dvd",
    ):
        self.host = host
        self.device = device
        self.code_store = code_store or IRCodeStore()
        self.discovery_timeout = discovery_timeout
        self.tv_target = tv_target
        self.dvd_target = dvd_target

        # Prototype state tracking. It prevents repeated MUTE decisions from
        # repeatedly pressing a toggle-style TV mute button.
        self._muted = False

    def connect(self) -> Any:
        """Discover/authenticate the BroadLink IR blaster if needed."""

        if self.device is not None:
            return self.device

        try:
            import broadlink  # type: ignore
        except ImportError as exc:
            raise InfraredError(
                "BroadLink hardware support is not installed. "
                "Run: pip install -r dvd/requirements-hardware.txt"
            ) from exc

        try:
            if self.host:
                device = broadlink.hello(self.host)
            else:
                discovered = broadlink.discover(
                    timeout=self.discovery_timeout
                )
                candidates = [
                    item
                    for item in discovered
                    if hasattr(item, "send_data")
                    and hasattr(item, "enter_learning")
                    and hasattr(item, "check_data")
                ]

                if not candidates:
                    raise InfraredError(
                        "No BroadLink IR blaster was discovered on the local network."
                    )

                device = candidates[0]

            device.auth()
        except InfraredError:
            raise
        except Exception as exc:
            raise InfraredError(
                "Could not connect/authenticate with the BroadLink IR blaster."
            ) from exc

        self.device = device
        return device

    def learn_command(
        self,
        target: str,
        command: RemoteCommand | str,
        *,
        timeout: float = 20.0,
        poll_interval: float = 0.5,
    ) -> bytes:
        """
        Learn one button from the user's physical remote and save it.

        The caller should tell the user which remote button to press before
        invoking this method.
        """

        device = self.connect()

        try:
            device.enter_learning()
        except Exception as exc:
            raise InfraredError("Could not enter IR learning mode.") from exc

        deadline = time.monotonic() + timeout
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                packet = device.check_data()
            except Exception as exc:
                # BroadLink devices commonly report "no learned packet yet"
                # while polling. Keep waiting until the timeout expires.
                last_error = exc
                packet = None

            if packet:
                captured = bytes(packet)
                self.code_store.set_code(target, command, captured)
                return captured

            time.sleep(poll_interval)

        message = (
            f"Timed out waiting to learn {target}/"
            f"{IRCodeStore._command_name(command)}."
        )
        raise InfraredError(message) from last_error

    def send_command(
        self,
        target: str,
        command: RemoteCommand | str,
    ) -> RemoteCommand | str:
        """Send a previously learned IR button press."""

        packet = self.code_store.get_code(target, command)
        if packet is None:
            raise InfraredError(
                f"No learned IR code exists for "
                f"{target}/{IRCodeStore._command_name(command)}."
            )

        device = self.connect()

        try:
            device.send_data(packet)
        except Exception as exc:
            raise InfraredError(
                f"Failed to send IR command to {target}."
            ) from exc

        return command

    def set_muted(self, muted: bool) -> RemoteCommand:
        """
        Put the TV into the requested mute state.

        Most television remotes expose one MUTE toggle button rather than
        separate mute/unmute buttons. If an explicit UNMUTE code has not been
        learned, ISweep safely reuses the learned MUTE toggle when leaving the
        state that this controller itself entered.
        """

        requested = bool(muted)
        if requested == self._muted:
            return RemoteCommand.MUTE if requested else RemoteCommand.UNMUTE

        if requested:
            self.send_command(self.tv_target, RemoteCommand.MUTE)
            self._muted = True
            return RemoteCommand.MUTE

        if self.code_store.has_code(self.tv_target, RemoteCommand.UNMUTE):
            self.send_command(self.tv_target, RemoteCommand.UNMUTE)
        else:
            self.send_command(self.tv_target, RemoteCommand.MUTE)

        self._muted = False
        return RemoteCommand.UNMUTE

    def execute_decision(self, decision: Decision) -> RemoteCommand:
        """
        Execute the hardware-safe subset of Decision Engine v1.

        MUTE sends a real TV mute command. ALLOW sends no IR command. A future
        scheduler/synchronization layer will decide exactly when to UNMUTE.
        """

        if decision.action == Action.MUTE:
            return self.set_muted(True)

        return RemoteCommand.ALLOW
