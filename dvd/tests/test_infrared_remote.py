from pathlib import Path

from dvd.control.commands import RemoteCommand
from dvd.control.infrared import BroadLinkInfraredRemote, IRCodeStore
from dvd.decision_engine import Action, Decision


class FakeBroadLinkDevice:
    def __init__(self):
        self.sent = []
        self.learn_packets = []
        self.learning_started = False

    def auth(self):
        return True

    def enter_learning(self):
        self.learning_started = True

    def check_data(self):
        if self.learn_packets:
            return self.learn_packets.pop(0)
        return b""

    def send_data(self, packet):
        self.sent.append(bytes(packet))


def make_store(tmp_path: Path) -> IRCodeStore:
    return IRCodeStore(tmp_path / "ir_codes.json")


def test_code_store_round_trip(tmp_path):
    store = make_store(tmp_path)
    packet = b"\x26\x00\x01\x02"

    store.set_code("tv", RemoteCommand.MUTE, packet)

    reloaded = IRCodeStore(tmp_path / "ir_codes.json")
    assert reloaded.get_code("tv", RemoteCommand.MUTE) == packet


def test_send_command_uses_learned_packet(tmp_path):
    device = FakeBroadLinkDevice()
    store = make_store(tmp_path)
    store.set_code("dvd", RemoteCommand.PLAY, b"play-code")

    remote = BroadLinkInfraredRemote(device=device, code_store=store)
    remote.send_command("dvd", RemoteCommand.PLAY)

    assert device.sent == [b"play-code"]


def test_learning_saves_packet(tmp_path):
    device = FakeBroadLinkDevice()
    device.learn_packets.append(b"learned-mute")
    store = make_store(tmp_path)

    remote = BroadLinkInfraredRemote(device=device, code_store=store)
    packet = remote.learn_command(
        "tv",
        RemoteCommand.MUTE,
        timeout=0.05,
        poll_interval=0.001,
    )

    assert device.learning_started is True
    assert packet == b"learned-mute"
    assert store.get_code("tv", RemoteCommand.MUTE) == b"learned-mute"


def test_mute_state_avoids_repeated_toggle(tmp_path):
    device = FakeBroadLinkDevice()
    store = make_store(tmp_path)
    store.set_code("tv", RemoteCommand.MUTE, b"mute-toggle")

    remote = BroadLinkInfraredRemote(device=device, code_store=store)

    remote.set_muted(True)
    remote.set_muted(True)

    assert device.sent == [b"mute-toggle"]


def test_unmute_can_reuse_mute_toggle(tmp_path):
    device = FakeBroadLinkDevice()
    store = make_store(tmp_path)
    store.set_code("tv", RemoteCommand.MUTE, b"mute-toggle")

    remote = BroadLinkInfraredRemote(device=device, code_store=store)

    remote.set_muted(True)
    remote.set_muted(False)

    assert device.sent == [b"mute-toggle", b"mute-toggle"]


def test_mute_decision_sends_real_mute_command(tmp_path):
    device = FakeBroadLinkDevice()
    store = make_store(tmp_path)
    store.set_code("tv", RemoteCommand.MUTE, b"mute-toggle")

    remote = BroadLinkInfraredRemote(device=device, code_store=store)
    decision = Decision(
        action=Action.MUTE,
        reason="test",
        detected_text="test word",
    )

    command = remote.execute_decision(decision)

    assert command == RemoteCommand.MUTE
    assert device.sent == [b"mute-toggle"]


def test_allow_decision_does_not_press_remote(tmp_path):
    device = FakeBroadLinkDevice()
    store = make_store(tmp_path)
    remote = BroadLinkInfraredRemote(device=device, code_store=store)

    decision = Decision(
        action=Action.ALLOW,
        reason="clean",
        detected_text="clean dialogue",
    )

    command = remote.execute_decision(decision)

    assert command == RemoteCommand.ALLOW
    assert device.sent == []
