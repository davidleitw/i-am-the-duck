# Public evaluation data

Three questions so far, each with its own fixture; the third fixture is private. Raw source runs remain local; this directory contains only public metrics, sanitized visible assistant text where the fixture is public, and the blind reviews.

Every anonymous reply pack is given to two blind reviewers at once, Claude Fable 5.1 and GPT-6 Astra, who rate clarity, coverage and faithfulness on an ordinal 1 to 5 scale and state a per-pair preference before the arm key is opened. The first slice predates this rule and has a single GPT-6 Astra read.

## job-recovery (first slice)

Opus 5 high has 3 pairs (6 runs); Luna max has 4 pairs (8 runs), 14 runs total.

- [initial-data.json](initial-data.json): per-run public IDs, provider/model/effort, arm, skill version hash, usage fields, elapsed time, and cost estimate.
- [initial-responses.md](initial-responses.md): all 14 complete visible assistant-message sequences, including progress and final messages; no thinking, system, debug, or raw sessions.
- [job-recovery.json](../cases/job-recovery.json): sanitized public copy of the source case.
- [astra-summary.md](astra-summary.md) and [astra-review.json](astra-review.json): GPT-6 Astra blind review.

Metrics are arithmetic means within each model and arm. `visible_characters` is the source assistant-visible Unicode code-point count; `public_visible_characters` records the count after privacy redaction, which can shorten text. Output tokens use the provider's recorded field. Opus keeps Anthropic result-usage fields; Luna keeps Codex turn-usage fields and they are not mixed. Opus cost is a source CLI list estimate, not a bill; Luna has no comparable saved cost field and remains null.

From the data: Duck versus Off is Opus reply characters -33.2%, output tokens -49.8%, elapsed -43.7%, cost estimate -38.6%; Luna reply characters -5.7% and output tokens +2.3%. Astra's blind read found clarity for Duck twice, Off twice, tied three times; decision help favored each side three times with one tie.

## retention-prune (second slice)

Opus 5 high, 2 pairs (4 runs). See [retention-prune-summary.md](retention-prune-summary.md).

- [retention-prune-data.json](retention-prune-data.json) and [retention-prune-responses.md](retention-prune-responses.md): same schema and rules as above, plus thinking tokens, permission-denial counts and hook evidence per run.
- [retention-prune.json](../cases/retention-prune.json): the public case; fixture under [fixtures/retention-prune](../fixtures/retention-prune).
- [fable-review.json](fable-review.json) and [gpt6-astra-review-retention-prune.json](gpt6-astra-review-retention-prune.json): the two blind reviews.

From the data: Duck versus Off is reply characters -44.3%, output tokens -32.0%, elapsed -30.6%, cost estimate -24.5%. Both reviewers preferred the Duck reply for decision help in both pairs; clarity favored Duck three times and tied once.

## design-status (third slice, private fixture)

Opus 5 high, 3 Off and 4 Duck runs. See [design-status-summary.md](design-status-summary.md) and [design-status-data.json](design-status-data.json).

The fixture is a snapshot of the owner's own repository plus seven design-review documents from a real session in which Opus 4.8 had answered a status question in the documents' code names and the owner could not follow. The fixture and reply texts stay private; usage, the reviewer form and all scores are published.

From the data: Duck versus Off is final reply characters -31.8%, output tokens -30.2%, elapsed -25.3%, cost estimate -21.6%, one-directional across all seven runs. Three blind readers (Fable 5.1, GPT-6 Astra, the interpreter) each found exactly one reply with at most one unexplained term, the same Duck reply; two chose it as the reply to act on, one chose an Off reply for completeness. Substance was even: one Duck reply carried a stale next step, two Off replies stated reviewer claims as verified.

## Chart

[initial-results.svg](../assets/initial-results.svg) shows reply characters and output tokens with Off fixed at 100%, one group per task, all on Opus 5 high. The GPT-5.6 Luna group from the first slice was dropped from the chart because its effect on length was within noise (-5.7% characters, +2.3% output tokens); the data stays in [initial-data.json](initial-data.json).

These are small samples, two synthetic questions and one private real one, and cannot support general readability, correctness, or cost claims. Fewer tokens do not establish better correctness; the reviews are judgments, not statistical proof.
