from types import SimpleNamespace

from dvd.playback import MediaKind, MediaSource, PlaybackStatus
from dvd.playback.vlc import VLCPlaybackController, dvd_mrl


class FakeMediaPlayer:
    def __init__(self):
        self.media = None
        self.time_ms = 10_000
        self.length_ms = 60_000
        self.volume = 80
        self.muted = False
        self.state = "stopped"
        self.hwnd = None

    def set_media(self, media):
        self.media = media

    def play(self):
        self.state = "playing"

    def set_pause(self, paused):
        if paused:
            self.state = "paused"

    def stop(self):
        self.state = "stopped"

    def audio_set_mute(self, value):
        self.muted = bool(value)

    def audio_get_mute(self):
        return int(self.muted)

    def audio_get_volume(self):
        return self.volume

    def get_time(self):
        return self.time_ms

    def get_length(self):
        return self.length_ms

    def set_time(self, value):
        self.time_ms = value

    def get_state(self):
        return self.state

    def set_hwnd(self, hwnd):
        self.hwnd = hwnd


class FakeInstance:
    def __init__(self, player):
        self.player = player
        self.created_media = []

    def media_player_new(self):
        return self.player

    def media_new(self, location):
        self.created_media.append(location)
        return f"media:{location}"


class FakeVLC:
    State = SimpleNamespace(Playing="playing", Paused="paused")


def make_controller():
    player = FakeMediaPlayer()
    instance = FakeInstance(player)
    controller = VLCPlaybackController(vlc_module=FakeVLC(), instance=instance)
    return controller, player, instance


def test_dvd_mrl_converts_windows_drive():
    assert dvd_mrl("D:\\") == "dvd:///D:/"
    assert dvd_mrl("E:/") == "dvd:///E:/"


def test_vlc_controller_loads_dvd_as_dvd_media_location():
    controller, player, instance = make_controller()

    source = MediaSource(MediaKind.DVD, "D:\\", "Test DVD")
    controller.load(source)

    assert instance.created_media == ["dvd:///D:/"]
    assert player.media == "media:dvd:///D:/"


def test_vlc_controller_controls_play_pause_and_mute():
    controller, player, _ = make_controller()
    controller.load(MediaSource(MediaKind.STREAM, "https://example.test/video"))

    controller.play()
    assert controller.get_state().status == PlaybackStatus.PLAYING

    controller.pause()
    assert controller.get_state().status == PlaybackStatus.PAUSED

    controller.mute()
    assert controller.get_state().muted is True

    controller.unmute()
    assert controller.get_state().muted is False


def test_vlc_controller_seeks_relative_and_clamps_to_duration():
    controller, player, _ = make_controller()

    controller.seek_relative(15)
    assert player.time_ms == 25_000

    controller.seek_relative(100)
    assert player.time_ms == 60_000

    controller.seek_relative(-100)
    assert player.time_ms == 0


def test_vlc_controller_exposes_real_clock_and_volume():
    controller, player, _ = make_controller()
    source = MediaSource(MediaKind.FILE, "movie.mp4", "movie.mp4")
    controller.load(source)
    player.time_ms = 12_500
    player.length_ms = 90_000
    player.volume = 65

    state = controller.get_state()

    assert state.source == source
    assert state.position_seconds == 12.5
    assert state.duration_seconds == 90.0
    assert state.volume == 0.65
