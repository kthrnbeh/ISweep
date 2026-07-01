# ISweep Speech Lab

ISweep Speech Lab provides a benchmark and dataset foundation for evaluating local STT quality and caption timing under ISweep constraints.

Scope and safety boundaries:
- Active-tab audio only in product runtime.
- No microphone path added here.
- No changes to selected-word mute runtime logic.
- No /event, skip, fast-forward, or playbackRate behavior introduced.
- No backend autostart behavior changes.

## Directory Layout

- `manifests/`: benchmark dataset manifests (JSONL)
- `scripts/`: validation, evaluation, and owned-audio augmentation tools
- `reports/`: generated metric reports

## Manifest Contract

Each JSONL line must include:
- `id`: unique sample ID
- `audio_path`: path to owned/consented local audio
- `transcript`: gold transcript text
- `selected_target_words`: words expected to be tracked for selected-word tests
- `word_timestamps`: exact gold word timing list with `word`, `start`, `end`
- `speaker_id`: stable speaker identifier
- `test_conditions`: metadata (`noise_level`, `room`, `device`, etc.)
- `consent`: boolean consent flag
- `source`: documented source metadata
- `license`: documented license metadata

See `manifests/gold_set.example.jsonl`.

## Validate Manifest

Run:

```bash
python speech_lab/scripts/validate_manifest.py --manifest speech_lab/manifests/gold_set.example.jsonl
```

Validation rejects:
- missing source or license documentation
- missing consent
- entries from random YouTube/movie/TV sources
- malformed or missing word timestamps

## Evaluate STT

Run:

```bash
python speech_lab/scripts/evaluate_stt.py \
  --manifest speech_lab/manifests/gold_set.example.jsonl \
  --predictions path/to/predictions.jsonl
```

Metrics:
- caption latency
- word error rate (WER)
- selected-word recall
- selected-word false-positive rate
- word timestamp error (ms)
- mute-leak duration
- over-mute duration

Model comparison is supported with local configured models, starting with current configured model and `base.en`.

Example:

```bash
python speech_lab/scripts/evaluate_stt.py \
  --manifest speech_lab/manifests/gold_set.example.jsonl \
  --predictions path/to/predictions.jsonl \
  --compare-models
```

## Safe Augmentation (Owned/Consented Audio Only)

Run:

```bash
python speech_lab/scripts/augment_owned_audio.py \
  --manifest speech_lab/manifests/gold_set.example.jsonl \
  --output-manifest speech_lab/manifests/gold_set.augmented.jsonl
```

Augmentations:
- speed variation
- volume variation
- simulated room echo
- synthetic noise

Guardrails:
- only entries with consent and documented source/license are processed
- no copyrighted third-party source audio is accepted

## Manual Import Notes (No Auto Download)

This lab intentionally does not auto-download large public datasets.

### Common Voice (manual)

1. Download from Mozilla Common Voice manually.
2. Keep original license and source attribution.
3. Convert selected clips to local paths.
4. Add manifest lines with:
   - full `source` fields
   - full `license` fields
   - explicit `consent`/dataset usage allowance

### LibriSpeech (manual)

1. Download manually from OpenSLR.
2. Keep source and license/provenance in each manifest entry.
3. Add speaker IDs and conditions metadata.
4. Do not include entries lacking documented provenance.
