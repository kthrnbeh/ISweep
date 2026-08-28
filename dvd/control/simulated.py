"""
ISweep DVD - Simulated Remote Controller

This controller does not control any real hardware.

Its purpose is to let us test the complete ISweep flow:

Detection
    ↓
Decision Engine
    ↓
Remote command

without requiring a television, DVD player, infrared transmitter,
or HDMI-CEC hardware.

Later, real controllers can use the same command interface.
"""

from dvd.control.commands import RemoteCommand
from dvd.decision_engine import Action, Decision


class SimulatedRemote:
    """
    Pretend ISweep remote controller.

    For now, commands are printed to the terminal so we can verify
    that the Decision Engine is requesting the correct action.
    """

    def execute_decision(self, decision: Decision) -> RemoteCommand:
        """
        Convert an ISweep Decision into a simulated remote command.
        """

        if decision.action == Action.MUTE:
            command = RemoteCommand.MUTE
        else:
            command = RemoteCommand.ALLOW

        self._print_command(command, decision)

        return command

    def _print_command(
        self,
        command: RemoteCommand,
        decision: Decision,
    ) -> None:
        """
        Display the simulated remote action.
        """

        print()
        print("=" * 55)
        print("ISWEEP DVD - SIMULATED REMOTE")
        print("=" * 55)
        print(f"Timestamp:     {decision.timestamp:.3f} seconds")
        print(f"Detected text: {decision.detected_text}")
        print(f"Decision:      {decision.action.value}")
        print(f"Command:       {command.value}")
        print(f"Reason:        {decision.reason}")

        if decision.matched_term:
            print(f"Matched term:  {decision.matched_term}")

        print("=" * 55)
        print()