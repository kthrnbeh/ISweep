import argparse
import json
import math
import os
from pathlib import Path
from typing import Any


def _tokenize(text: str) -> list[str]:
    return [part for part in str(text or "").strip().lower().split() if part]


def _levenshtein_distance(ref: list[str], hyp: list[str]) -> int:
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    dp = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        prev = dp[0]
        dp[0] = i
        for j, h in enumerate(hyp, start=1):
            cur = dp[j]
            if r == h:
                dp[j] = prev
            else:
                dp[j] = min(prev + 1, dp[j] + 1, dp[j - 1] + 1)
            prev = cur
    return dp[-1]


def word_error_rate(reference_text: str, predicted_text: str) -> float:
    ref_tokens = _tokenize(reference_text)
    pred_tokens = _tokenize(predicted_text)
    if not ref_tokens:
        return 0.0 if not pred_tokens else 1.0
    return _levenshtein_distance(ref_tokens, pred_tokens) / float(len(ref_tokens))


def caption_latency_ms(capture_started_at: int | None, overlay_rendered_at: int | None) -> float:
    if capture_started_at is None or overlay_rendered_at is None:
        return math.nan
    return float(max(int(overlay_rendered_at) - int(capture_started_at), 0))


def selected_word_metrics(
    selected_target_words: list[str],
    gold_words: list[dict[str, Any]],
    predicted_words: list[dict[str, Any]],
) -> dict[str, float]:
    selected = {str(word).strip().lower() for word in selected_target_words if str(word).strip()}
    if not selected:
        return {"selected_word_recall": 1.0, "selected_word_false_positive_rate": 0.0}

    gold_selected = [str(entry.get("word") or "").strip().lower() for entry in gold_words if str(entry.get("word") or "").strip().lower() in selected]
    pred_selected = [str(entry.get("word") or "").strip().lower() for entry in predicted_words if str(entry.get("word") or "").strip().lower() in selected]

    true_positives = 0
    gold_remaining = list(gold_selected)
    for word in pred_selected:
        if word in gold_remaining:
            true_positives += 1
            gold_remaining.remove(word)

    false_positives = max(len(pred_selected) - true_positives, 0)
    recall = true_positives / float(len(gold_selected)) if gold_selected else 1.0
    fp_rate = false_positives / float(len(pred_selected)) if pred_selected else 0.0
    return {
        "selected_word_recall": recall,
        "selected_word_false_positive_rate": fp_rate,
    }


def word_timestamp_error_ms(gold_words: list[dict[str, Any]], predicted_words: list[dict[str, Any]]) -> float:
    if not gold_words or not predicted_words:
        return math.nan
    total_error = 0.0
    pair_count = 0
    for idx, gold in enumerate(gold_words):
        if idx >= len(predicted_words):
            break
        pred = predicted_words[idx]
        try:
            g_start = float(gold.get("start"))
            g_end = float(gold.get("end"))
            p_start = float(pred.get("start"))
            p_end = float(pred.get("end"))
        except (TypeError, ValueError):
            continue
        start_err = abs(p_start - g_start) * 1000.0
        end_err = abs(p_end - g_end) * 1000.0
        total_error += (start_err + end_err) / 2.0
        pair_count += 1
    return (total_error / pair_count) if pair_count else math.nan


def mute_timing_errors_ms(gold_words: list[dict[str, Any]], predicted_words: list[dict[str, Any]], selected_target_words: list[str]) -> dict[str, float]:
    selected = {str(word).strip().lower() for word in selected_target_words if str(word).strip()}
    if not selected:
        return {"mute_leak_duration_ms": 0.0, "over_mute_duration_ms": 0.0}

    def _extract_windows(words: list[dict[str, Any]]) -> list[tuple[float, float]]:
        windows: list[tuple[float, float]] = []
        for word in words:
            token = str(word.get("word") or "").strip().lower()
            if token not in selected:
                continue
            try:
                start = float(word.get("start"))
                end = float(word.get("end"))
            except (TypeError, ValueError):
                continue
            if end < start:
                continue
            windows.append((start, end))
        return windows

    gold_windows = _extract_windows(gold_words)
    pred_windows = _extract_windows(predicted_words)

    leak_ms = 0.0
    over_ms = 0.0

    for g_start, g_end in gold_windows:
        overlap = 0.0
        for p_start, p_end in pred_windows:
            left = max(g_start, p_start)
            right = min(g_end, p_end)
            if right > left:
                overlap += right - left
        leak_ms += max((g_end - g_start) - overlap, 0.0) * 1000.0

    for p_start, p_end in pred_windows:
        overlap = 0.0
        for g_start, g_end in gold_windows:
            left = max(g_start, p_start)
            right = min(g_end, p_end)
            if right > left:
                overlap += right - left
        over_ms += max((p_end - p_start) - overlap, 0.0) * 1000.0

    return {
        "mute_leak_duration_ms": leak_ms,
        "over_mute_duration_ms": over_ms,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            row = raw.strip()
            if not row:
                continue
            rows.append(json.loads(row))
    return rows


def evaluate_manifest_and_predictions(gold_entries: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    predictions_by_id = {str(entry.get("id")): entry for entry in predictions}

    latencies: list[float] = []
    wers: list[float] = []
    recalls: list[float] = []
    fp_rates: list[float] = []
    ts_errors: list[float] = []
    mute_leaks: list[float] = []
    over_mutes: list[float] = []
    line_alignment_success: list[float] = []

    for gold in gold_entries:
        sample_id = str(gold.get("id"))
        pred = predictions_by_id.get(sample_id, {})

        gold_text = str(gold.get("transcript") or "")
        pred_text = str(pred.get("text") or "")
        wer = word_error_rate(gold_text, pred_text)
        wers.append(wer)

        latency = caption_latency_ms(pred.get("capture_started_at"), pred.get("overlay_rendered_at"))
        if not math.isnan(latency):
            latencies.append(latency)

        gold_words = gold.get("word_timestamps") if isinstance(gold.get("word_timestamps"), list) else []
        pred_words = pred.get("word_timestamps") if isinstance(pred.get("word_timestamps"), list) else []
        selected = gold.get("selected_target_words") if isinstance(gold.get("selected_target_words"), list) else []

        selected_metrics = selected_word_metrics(selected, gold_words, pred_words)
        recalls.append(selected_metrics["selected_word_recall"])
        fp_rates.append(selected_metrics["selected_word_false_positive_rate"])

        tse = word_timestamp_error_ms(gold_words, pred_words)
        if not math.isnan(tse):
            ts_errors.append(tse)

        mute_metrics = mute_timing_errors_ms(gold_words, pred_words, selected)
        mute_leaks.append(mute_metrics["mute_leak_duration_ms"])
        over_mutes.append(mute_metrics["over_mute_duration_ms"])

        alignment_status = str(pred.get("alignment_status") or pred.get("reference_alignment_status") or "").strip().lower()
        if alignment_status:
            line_alignment_success.append(1.0 if alignment_status == "aligned" else 0.0)

    def _avg(values: list[float]) -> float:
        return (sum(values) / float(len(values))) if values else 0.0

    return {
        "sample_count": len(gold_entries),
        "caption_latency_ms": _avg(latencies),
        "word_error_rate": _avg(wers),
        "selected_word_recall": _avg(recalls),
        "selected_word_false_positive_rate": _avg(fp_rates),
        "line_alignment_success_rate": _avg(line_alignment_success),
        "word_timestamp_error_ms": _avg(ts_errors),
        "mute_leak_duration_ms": _avg(mute_leaks),
        "over_mute_duration_ms": _avg(over_mutes),
    }


def _parse_available_model_names() -> set[str]:
    raw = str(os.getenv("ISWEEP_STT_AVAILABLE_MODELS", "") or "").strip()
    if not raw:
        return set()
    return {
        part.strip()
        for part in raw.split(',')
        if part.strip()
    }


def get_model_comparison_config() -> dict[str, Any]:
    configured_model = str(os.getenv("ISWEEP_STT_MODEL_SIZE", "base") or "base").strip() or "base"
    available = _parse_available_model_names()

    candidate_models: list[str] = []
    for name in [configured_model, "base.en"]:
        if name and name not in candidate_models:
            candidate_models.append(name)

    # Include small.en only if explicitly configured or already locally available.
    if configured_model == "small.en" or "small.en" in available:
        if "small.en" not in candidate_models:
            candidate_models.append("small.en")

    return {
        "configured_model": configured_model,
        "candidate_models": candidate_models,
        "selected_comparison_models": candidate_models,
        "available_models_hint": sorted(list(available)),
        "download_policy": "no_automatic_model_downloads",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate STT predictions against Speech Lab manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--predictions", required=False, type=Path)
    parser.add_argument("--report", required=False, type=Path)
    parser.add_argument("--compare-models", action="store_true")
    args = parser.parse_args()

    gold_entries = _load_jsonl(args.manifest)
    predictions = _load_jsonl(args.predictions) if args.predictions else []

    metrics = evaluate_manifest_and_predictions(gold_entries, predictions)
    payload: dict[str, Any] = {"metrics": metrics}

    if args.compare_models:
        payload["model_comparison"] = get_model_comparison_config()

    output = json.dumps(payload, indent=2)
    print(output)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
