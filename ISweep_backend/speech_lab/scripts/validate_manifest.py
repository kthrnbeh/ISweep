import argparse
import json
from pathlib import Path
from typing import Any

REJECTED_SOURCE_MARKERS = {
    "youtube",
    "yt",
    "movie",
    "tv",
    "netflix",
    "hulu",
    "disney",
    "prime video",
    "broadcast",
}

REQUIRED_FIELDS = {
    "id",
    "audio_path",
    "transcript",
    "selected_target_words",
    "word_timestamps",
    "speaker_id",
    "test_conditions",
    "consent",
    "source",
    "license",
}


def _contains_rejected_source_text(value: str) -> bool:
    text = str(value or "").strip().lower()
    return any(marker in text for marker in REJECTED_SOURCE_MARKERS)


def _validate_source(source: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(source, dict):
        return ["source must be an object"]

    for field in ("type", "dataset", "reference", "collection_method"):
        if not str(source.get(field) or "").strip():
            errors.append(f"source.{field} is required")

    source_blob = " ".join(str(source.get(k) or "") for k in source.keys())
    if _contains_rejected_source_text(source_blob):
        errors.append("source indicates random YouTube/movie/TV origin, which is not allowed")

    return errors


def _validate_license(license_info: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(license_info, dict):
        return ["license must be an object"]
    if not str(license_info.get("name") or "").strip():
        errors.append("license.name is required")
    if not str(license_info.get("url") or "").strip():
        errors.append("license.url is required")
    return errors


def _validate_word_timestamps(word_timestamps: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(word_timestamps, list) or not word_timestamps:
        return ["word_timestamps must be a non-empty list"]

    prev_end = -1.0
    for idx, entry in enumerate(word_timestamps):
        if not isinstance(entry, dict):
            errors.append(f"word_timestamps[{idx}] must be an object")
            continue
        word = str(entry.get("word") or "").strip()
        if not word:
            errors.append(f"word_timestamps[{idx}].word is required")
        try:
            start = float(entry.get("start"))
            end = float(entry.get("end"))
        except (TypeError, ValueError):
            errors.append(f"word_timestamps[{idx}] start/end must be numeric")
            continue
        if end < start:
            errors.append(f"word_timestamps[{idx}] end must be >= start")
        if start < prev_end:
            errors.append(f"word_timestamps[{idx}] starts before previous word ends")
        prev_end = max(prev_end, end)
    return errors


def validate_entry(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return ["entry must be an object"]

    missing = sorted(REQUIRED_FIELDS.difference(entry.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    if not str(entry.get("id") or "").strip():
        errors.append("id is required")
    if not str(entry.get("audio_path") or "").strip():
        errors.append("audio_path is required")
    if not str(entry.get("transcript") or "").strip():
        errors.append("transcript is required")
    if not str(entry.get("speaker_id") or "").strip():
        errors.append("speaker_id is required")

    selected = entry.get("selected_target_words")
    if not isinstance(selected, list):
        errors.append("selected_target_words must be a list")
    elif any(not str(word or "").strip() for word in selected):
        errors.append("selected_target_words must not include empty values")

    if entry.get("consent") is not True:
        errors.append("consent must be true")

    conditions = entry.get("test_conditions")
    if not isinstance(conditions, dict) or not conditions:
        errors.append("test_conditions must be a non-empty object")

    errors.extend(_validate_source(entry.get("source")))
    errors.extend(_validate_license(entry.get("license")))
    errors.extend(_validate_word_timestamps(entry.get("word_timestamps")))

    return errors


def validate_manifest_file(manifest_path: Path) -> list[str]:
    issues: list[str] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            row = raw.strip()
            if not row:
                continue
            try:
                entry = json.loads(row)
            except json.JSONDecodeError as exc:
                issues.append(f"line {line_no}: invalid JSON ({exc})")
                continue
            for error in validate_entry(entry):
                issues.append(f"line {line_no}: {error}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Speech Lab manifest JSONL")
    parser.add_argument("--manifest", required=True, type=Path, help="Path to manifest JSONL file")
    args = parser.parse_args()

    issues = validate_manifest_file(args.manifest)
    if issues:
        print("Manifest validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Manifest validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
