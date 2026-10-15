# ISweep development rules

## Working agreement

- Build on existing working behavior; do not replace a working architecture.
- Inspect the current implementation, repository instructions, and existing tests before editing.
- Make the smallest focused change that satisfies the task.
- Never modify or delete anything under `/dvd` during ISweep extension, backend, or documentation work.
- Do not create a commit until the exact diff and test results have been reviewed by the user.

## Required task reporting

- Before editing, show an accomplishment summary and the expected edits.
- Before committing, report the exact diff summary and test results.
- Final task reports must include exact files changed, tests run, live verification status, and remaining limitations.
- Never print authentication tokens or claim live browser verification unless Codex actually observed the result.

## Behavior that must remain stable

Unless a task explicitly says otherwise:

- Preserve native caption fallback unless valid ISweep captions are already available.
- Preserve caption masking, draggable caption positioning, and caption sizes: Small 14px, Medium 18px, and Large 20px.
- Preserve source-based timing.
- Never change YouTube playback speed.
- Enabling captions must not mute or alter normal audio.
- Only selected-word detection may request temporary muting.
- Restore the user's previous audio state, including leaving already-muted YouTube audio muted.
- Do not rewrite the existing caption architecture or create a second synchronization or caption-masking path.

## Verification expectations

- Reuse existing synchronization, caption, and audio test utilities before creating new ones.
- Verify the Filter selection path through `blocklist.items`, backend response, extension storage, and `selectedWordCount`.
- Verify whole-word masking, including case and punctuation, while leaving words such as `shell` unchanged.
- Verify missing authentication and missing word data fail clearly rather than reporting false synchronization success.
- Run relevant JavaScript, Python, manifest, synchronization, caption, timing, audio-safety, backend, `git diff --check`, and `/dvd`-change checks when applicable.
- Use browser/computer verification only after automated tests pass. If it is unavailable, provide manual steps and state that live behavior was not verified.
