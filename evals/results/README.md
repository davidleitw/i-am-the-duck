# Initial job-recovery data

This public slice fixes one question and one fixture: `job-recovery`. Opus 5 high has 3 pairs (6 runs); Luna max has 4 pairs (8 runs), 14 runs total. Raw source runs remain local; this directory contains only public metrics and sanitized visible assistant text.

- [initial-data.json](initial-data.json): per-run public IDs, provider/model/effort, arm, skill version hash, usage fields, elapsed time, and cost estimate.
- [initial-responses.md](initial-responses.md): all 14 complete visible assistant-message sequences, including progress and final messages; no thinking, system, debug, or raw sessions.
- [initial-results.svg](../assets/initial-results.svg): Reply characters and Output tokens, with Off fixed at 100%.
- [job-recovery.json](../cases/job-recovery.json): sanitized public copy of the source case.

Metrics are arithmetic means within each model and arm. `visible_characters` is the source assistant-visible Unicode code-point count; `public_visible_characters` records the count after privacy redaction, which can shorten text. Output tokens use the provider's recorded field. Opus keeps Anthropic result-usage fields; Luna keeps Codex turn-usage fields and they are not mixed. Opus cost is a source CLI list estimate, not a bill; Luna has no comparable saved cost field and remains null.

From the data: Duck versus Off is Opus Reply characters -33.17% and Output tokens -49.77%; Luna Reply characters -5.70% and Output tokens +2.28%. The +2.3% result remains visible; fewer output tokens do not establish better correctness.

This is one synthetic question with 3/4 pairs per model, so it cannot support general readability, correctness, or cost claims. The fixed permission allowlist rejected some extra probes; those denials remain in local raw evidence and were not treated as successful verification.

Astra subsequently read and scored every complete visible response before the arm key was revealed. [Review and mapping](astra-summary.md) and [locked assessment](astra-review.json) are included. It found mixed clarity and decision-help results, not an overall winner; these judgments are separate from the length and usage measurements.
