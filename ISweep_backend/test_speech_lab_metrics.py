from speech_lab.scripts.evaluate_stt import (
    caption_latency_ms,
    evaluate_manifest_and_predictions,
    mute_timing_errors_ms,
    selected_word_metrics,
    word_error_rate,
    word_timestamp_error_ms,
)


def test_word_error_rate_basic():
    assert word_error_rate("hello there", "hello there") == 0.0
    assert word_error_rate("hello there", "hello") > 0.0


def test_caption_latency_ms_basic():
    assert caption_latency_ms(1000, 1400) == 400.0


def test_selected_word_metrics_and_timestamp_error():
    gold_words = [
        {"word": "hello", "start": 0.1, "end": 0.3},
        {"word": "test", "start": 0.4, "end": 0.6},
    ]
    pred_words = [
        {"word": "hello", "start": 0.12, "end": 0.32},
        {"word": "test", "start": 0.42, "end": 0.61},
    ]

    metrics = selected_word_metrics(["test"], gold_words, pred_words)
    assert metrics["selected_word_recall"] == 1.0
    assert metrics["selected_word_false_positive_rate"] == 0.0

    ts_err = word_timestamp_error_ms(gold_words, pred_words)
    assert ts_err >= 0.0


def test_mute_timing_error_metrics():
    gold_words = [{"word": "test", "start": 1.0, "end": 1.3}]
    pred_words = [{"word": "test", "start": 1.05, "end": 1.2}]

    metrics = mute_timing_errors_ms(gold_words, pred_words, ["test"])
    assert metrics["mute_leak_duration_ms"] >= 0.0
    assert metrics["over_mute_duration_ms"] >= 0.0


def test_evaluate_manifest_and_predictions_outputs_all_required_metrics():
    gold_entries = [
        {
            "id": "s1",
            "transcript": "hello test",
            "selected_target_words": ["test"],
            "word_timestamps": [
                {"word": "hello", "start": 0.1, "end": 0.3},
                {"word": "test", "start": 0.4, "end": 0.6},
            ],
        }
    ]
    predictions = [
        {
            "id": "s1",
            "text": "hello test",
            "word_timestamps": [
                {"word": "hello", "start": 0.11, "end": 0.31},
                {"word": "test", "start": 0.41, "end": 0.61},
            ],
            "capture_started_at": 1000,
            "overlay_rendered_at": 1300,
        }
    ]

    report = evaluate_manifest_and_predictions(gold_entries, predictions)

    for key in (
        "caption_latency_ms",
        "word_error_rate",
        "selected_word_recall",
        "selected_word_false_positive_rate",
        "word_timestamp_error_ms",
        "mute_leak_duration_ms",
        "over_mute_duration_ms",
    ):
        assert key in report
