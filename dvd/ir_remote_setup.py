"""
ISweep DVD - BroadLink IR Setup Utility

Use this only after a BroadLink RM-series IR blaster has been added to
the same local network as this computer.

Examples:

    python -m dvd.ir_remote_setup learn tv MUTE
    python -m dvd.ir_remote_setup mute-test
    python -m dvd.ir_remote_setup learn dvd PLAY
    python -m dvd.ir_remote_setup send dvd PLAY

The learned packets are stored in dvd/config/ir_codes.json on the local
computer. That file is intentionally ignored by Git.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dvd.control.commands import RemoteCommand
from dvd.control.infrared import BroadLinkInfraredRemote, InfraredError


def parse_command(value: str) -> RemoteCommand:
    try:
        return RemoteCommand(value.strip().upper())
    except ValueError as exc:
        choices = ", ".join(command.value for command in RemoteCommand)
        raise argparse.ArgumentTypeError(
            f"Unknown remote command {value!r}. Choose one of: {choices}"
        ) from exc


def create_remote(args: argparse.Namespace) -> BroadLinkInfraredRemote:
    host = args.host or os.getenv("ISWEEP_IR_HOST") or None
    return BroadLinkInfraredRemote(host=host)


def learn(args: argparse.Namespace) -> int:
    remote = create_remote(args)
    command = args.command

    print()
    print("=" * 60)
    print("ISWEEP DVD - LEARN IR BUTTON")
    print("=" * 60)
    print(f"Target:  {args.target}")
    print(f"Command: {command.value}")
    print()
    print("When the BroadLink learning light appears, point the ORIGINAL")
    print("remote at the BroadLink and press the requested button once.")
    print()

    remote.learn_command(args.target, command, timeout=args.timeout)

    print(f"Learned and saved {args.target}/{command.value}.")
    return 0


def send(args: argparse.Namespace) -> int:
    remote = create_remote(args)
    remote.send_command(args.target, args.command)
    print(f"Sent {args.target}/{args.command.value}.")
    return 0


def mute_test(args: argparse.Namespace) -> int:
    remote = create_remote(args)

    print()
    print("ISweep will press the TV mute button now.")
    remote.set_muted(True)
    print(f"Waiting {args.seconds:.1f} seconds...")
    time.sleep(args.seconds)
    print("ISweep will unmute now.")
    remote.set_muted(False)
    print("Mute/unmute test complete.")
    return 0


def dvd_test(args: argparse.Namespace) -> int:
    remote = create_remote(args)
    commands = [
        RemoteCommand.PLAY,
        RemoteCommand.PAUSE,
        RemoteCommand.PLAY,
        RemoteCommand.FAST_FORWARD,
        RemoteCommand.PLAY,
        RemoteCommand.SKIP,
    ]

    print()
    print("DVD remote-control test starting.")
    print("Each learned command will be sent with a short pause between them.")
    print()

    for command in commands:
        print(f"Sending DVD {command.value}...")
        remote.send_command("dvd", command)
        time.sleep(args.seconds)

    print("DVD remote-control test complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Learn and test real ISweep DVD infrared commands."
    )
    parser.add_argument(
        "--host",
        help=(
            "Optional BroadLink IP address. If omitted, ISweep discovers "
            "an IR blaster on the local network. You can also set "
            "ISWEEP_IR_HOST."
        ),
    )

    subparsers = parser.add_subparsers(dest="action", required=True)

    learn_parser = subparsers.add_parser(
        "learn",
        help="Learn one button from an existing physical remote.",
    )
    learn_parser.add_argument("target", choices=["tv", "dvd"])
    learn_parser.add_argument("command", type=parse_command)
    learn_parser.add_argument("--timeout", type=float, default=20.0)
    learn_parser.set_defaults(handler=learn)

    send_parser = subparsers.add_parser(
        "send",
        help="Send one previously learned button.",
    )
    send_parser.add_argument("target", choices=["tv", "dvd"])
    send_parser.add_argument("command", type=parse_command)
    send_parser.set_defaults(handler=send)

    mute_parser = subparsers.add_parser(
        "mute-test",
        help="Mute the TV, wait, then unmute it.",
    )
    mute_parser.add_argument("--seconds", type=float, default=2.0)
    mute_parser.set_defaults(handler=mute_test)

    dvd_parser = subparsers.add_parser(
        "dvd-test",
        help="Send a short PLAY/PAUSE/FF/SKIP hardware test sequence.",
    )
    dvd_parser.add_argument("--seconds", type=float, default=1.0)
    dvd_parser.set_defaults(handler=dvd_test)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return int(args.handler(args))
    except InfraredError as exc:
        print()
        print("ISweep IR hardware error:")
        print(f"  {exc}")
        print()
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
