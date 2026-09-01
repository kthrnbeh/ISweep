from dvd.playback.disc import looks_like_dvd_video


def test_video_ts_directory_is_recognized_as_dvd_video(tmp_path):
    (tmp_path / "VIDEO_TS").mkdir()

    assert looks_like_dvd_video(tmp_path) is True


def test_normal_directory_is_not_recognized_as_dvd_video(tmp_path):
    (tmp_path / "MOVIES").mkdir()

    assert looks_like_dvd_video(tmp_path) is False
