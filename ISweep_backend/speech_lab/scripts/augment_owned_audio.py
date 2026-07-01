import argparse
import json
import random
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np

BLOCKED_SOURCE_MARKERS = {"youtube", "movie", "tv", "netflix", "hulu", "disney", "broadcast"}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            row = raw.strip()
            if not row:
                continue
            rows.append(json.loads(row))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _is_owned_or_consented(entry: dict[str, Any]) -> bool:
    if entry.get("consent") is not True:
        return False
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    source_blob = " ".join(str(source.get(k) or "") for k in source.keys()).lower()
    if any(marker in source_blob for marker in BLOCKED_SOURCE_MARKERS):
        return False
    if not str(entry.get("license") if isinstance(entry.get("license"), str) else (entry.get("license") or {}).get("name") or "").strip():
        return False
    if not str(entry.get("audio_path") or "").strip():
        return False
    return True


def _read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise ValueError(f"Only 16-bit PCM WAV is supported for augmentation: {path}")

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        total = samples.size // channels
        samples = samples[: total * channels].reshape(total, channels).mean(axis=1)
    return samples.astype(np.float32, copy=False), int(sample_rate)


def _write_wav_mono(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(samples.astype(np.float32, copy=False), -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm16.tobytes())


def _resample_linear(samples: np.ndarray, factor: float) -> np.ndarray:
    if factor <= 0:
        return samples
    if samples.size == 0:
        return samples
    source_idx = np.arange(samples.size, dtype=np.float32)
    target_len = max(int(samples.size / factor), 1)
    target_idx = np.linspace(0, samples.size - 1, target_len, dtype=np.float32)
    return np.interp(target_idx, source_idx, samples).astype(np.float32)


def _apply_echo(samples: np.ndarray, sample_rate: int, delay_ms: float = 80.0, decay: float = 0.35) -> np.ndarray:
    delay_samples = max(int((delay_ms / 1000.0) * sample_rate), 1)
    out = np.copy(samples)
    if delay_samples < samples.size:
        out[delay_samples:] += samples[:-delay_samples] * float(decay)
    return np.clip(out, -1.0, 1.0)


def _apply_noise(samples: np.ndarray, noise_level: float = 0.01) -> np.ndarray:
    noise = np.random.normal(0.0, float(noise_level), size=samples.shape).astype(np.float32)
    out = samples + noise
    return np.clip(out, -1.0, 1.0)


def augment_entry_audio(audio_path: Path, output_dir: Path) -> list[tuple[str, Path]]:
    samples, sample_rate = _read_wav_mono(audio_path)
    stem = audio_path.stem

    outputs: list[tuple[str, Path]] = []

    speed_factor = random.choice([0.9, 1.1])
    speed_samples = _resample_linear(samples, speed_factor)
    speed_path = output_dir / f"{stem}.aug_speed_{speed_factor:.1f}.wav"
    _write_wav_mono(speed_path, speed_samples, sample_rate)
    outputs.append(("speed_variation", speed_path))

    gain = random.choice([0.75, 1.25])
    volume_samples = np.clip(samples * gain, -1.0, 1.0)
    volume_path = output_dir / f"{stem}.aug_volume_{gain:.2f}.wav"
    _write_wav_mono(volume_path, volume_samples, sample_rate)
    outputs.append(("volume_variation", volume_path))

    echo_samples = _apply_echo(samples, sample_rate, delay_ms=80.0, decay=0.35)
    echo_path = output_dir / f"{stem}.aug_echo.wav"
    _write_wav_mono(echo_path, echo_samples, sample_rate)
    outputs.append(("room_echo", echo_path))

    noise_samples = _apply_noise(samples, noise_level=0.01)
    noise_path = output_dir / f"{stem}.aug_noise.wav"
    _write_wav_mono(noise_path, noise_samples, sample_rate)
    outputs.append(("synthetic_noise", noise_path))

    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Augment owned/consented Speech Lab audio")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--output-manifest", required=False, type=Path)
    args = parser.parse_args()

    entries = _load_jsonl(args.manifest)
    augmented_manifest_rows: list[dict[str, Any]] = []

    for entry in entries:
        if not _is_owned_or_consented(entry):
            raise ValueError(
                f"Refusing augmentation for entry '{entry.get('id')}'. "
                "Only owned/consented entries with documented source/license are allowed."
            )

        audio_path = Path(str(entry.get("audio_path")))
        if not audio_path.is_absolute():
            audio_path = (args.manifest.parent / audio_path).resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        outputs = augment_entry_audio(audio_path, args.output_dir)
        for aug_type, out_path in outputs:
            row = dict(entry)
            row["id"] = f"{entry.get('id')}-{aug_type}"
            row["audio_path"] = str(out_path)
            row["augmentation"] = {
                "type": aug_type,
                "safe_owned_only": True,
                "copyrighted_source_audio_allowed": False,
            }
            augmented_manifest_rows.append(row)

    output_manifest = args.output_manifest or (args.output_dir / "augmented_manifest.jsonl")
    _write_jsonl(output_manifest, augmented_manifest_rows)
    print(f"Wrote {len(augmented_manifest_rows)} augmented entries to {output_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
