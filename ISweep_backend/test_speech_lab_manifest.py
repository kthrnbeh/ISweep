import json
from pathlib import Path

from speech_lab.scripts.validate_manifest import validate_manifest_file


def _write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _valid_entry() -> dict:
    return {
        "id": "sample-1",
        "audio_path": "owned_audio/sample-1.wav",
        "transcript": "hello test",
        "selected_target_words": ["test"],
        "word_timestamps": [
            {"word": "hello", "start": 0.1, "end": 0.3},
            {"word": "test", "start": 0.31, "end": 0.5},
        ],
        "speaker_id": "speaker_a",
        "test_conditions": {"environment": "quiet_room"},
        "consent": True,
        "source": {
            "type": "owned_recording",
            "dataset": "isweep_owned",
            "reference": "batch-1",
            "collection_method": "consented_read_prompt",
        },
        "license": {"name": "internal", "url": "https://example.local/license"},
    }


def test_validate_manifest_passes_for_valid_entry(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(manifest, [_valid_entry()])

    issues = validate_manifest_file(manifest)
    assert issues == []


def test_validate_manifest_rejects_missing_source_or_license(tmp_path):
    entry = _valid_entry()
    entry.pop("source")
    entry.pop("license")

    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(manifest, [entry])

    issues = validate_manifest_file(manifest)
    assert any("source" in issue for issue in issues)
    assert any("license" in issue for issue in issues)


def test_validate_manifest_rejects_blocked_youtube_movie_tv_source(tmp_path):
    entry = _valid_entry()
    entry["source"]["dataset"] = "random youtube clip"

    manifest = tmp_path / "manifest.jsonl"
    _write_jsonl(manifest, [entry])

    issues = validate_manifest_file(manifest)
    assert any("YouTube/movie/TV" in issue for issue in issues)
