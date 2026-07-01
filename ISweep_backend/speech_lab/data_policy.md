# ISweep Speech Lab Data Policy

## Allowed Data

Allowed entries must be one of:
- owned recordings with explicit consent
- datasets with documented license and usage rights

Every entry must include:
- `source` metadata (origin and collection method)
- `license` metadata (name and reference URL/text)
- `consent: true` for owned/consented recordings, or documented dataset policy compatibility

## Rejected Data

Rejected immediately:
- missing source metadata
- missing license metadata
- unknown provenance audio
- random YouTube/movie/TV clips
- copyrighted media clips without explicit rights

## Copyright and Consent Rules

- Speech Lab never assumes fair-use permission for benchmark inclusion.
- Benchmarks must remain auditable for source and rights.
- Augmentation is only permitted for owned/consented source audio.

## Public Dataset Handling

- No automatic downloading in scripts.
- Manual import only with explicit provenance fields.
- Common Voice and LibriSpeech require source and license fields in each manifest line.

## Privacy

- Prefer pseudonymous `speaker_id` values.
- Avoid storing personal identifiers in manifest entries.
