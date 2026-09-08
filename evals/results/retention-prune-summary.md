# Retention-prune: data and two blind reviews

Second public slice. One question, one fixture: `retention-prune`, a small snapshot retention pruner whose operation notes disagree with the code in three places and whose tests leave the disputed combinations untested. Opus 5 high, 2 pairs (4 runs), all `ok`. Raw runs stay local; [retention-prune-data.json](retention-prune-data.json) holds the public metrics and [retention-prune-responses.md](retention-prune-responses.md) every visible assistant message.

## Usage and length

| Run | Messages | Reply chars | Output tokens | of which thinking | Elapsed | Cost estimate |
|---|---|---|---|---|---|---|
| p1 off | 8 | 7019 | 15232 | 7402 | 227 s | $0.667 |
| p1 duck | 4 | 4472 | 12371 | 4578 | 180 s | $0.569 |
| p2 off | 7 | 8329 | 19236 | 8346 | 268 s | $0.735 |
| p2 duck | 3 | 4074 | 11065 | 4823 | 163 s | $0.490 |

Means, Duck versus Off: reply characters -44.3%, output tokens -32.0%, elapsed -30.6%, cost estimate -24.5%. Cost is the Claude CLI's own estimate, not a bill. Thinking tokens come from the CLI's `output_tokens_details.thinking_tokens` field.

Runner evidence: both Duck runs had the complete skill text in the session-start hook output before the first reply and neither called the Skill tool again; both Off runs had no plugin in the init event. All four runs left the workspace unchanged. Each run had 1 to 3 permission denials, all probe scripts the fixed allowlist rejected; every reply disclosed this.

## Blind reviews

The same anonymous pack (question, fixture, both pairs with A/B labels) went to two reviewers who rated before any key was opened: Claude Fable 5.1 (the primary interpreter; it also authored the fixture, see [fable-review.json](fable-review.json)) and GPT-6 Astra at medium effort, read-only, asked to do nothing beyond scoring ([gpt6-astra-review-retention-prune.json](gpt6-astra-review-retention-prune.json)). Labels: in both pairs A was Off and B was Duck.

| Pair | Reviewer | A clarity/coverage/faithfulness | B clarity/coverage/faithfulness | Clarity preference | Decision-help preference |
|---|---|---|---|---|---|
| 01 | Fable 5.1 | 3 / 5 / 4 | 5 / 4 / 5 | Duck | Duck |
| 01 | GPT-6 Astra | 4 / 5 / 3 | 4 / 4 / 3 | Tie | Duck |
| 02 | Fable 5.1 | 3 / 5 / 3 | 5 / 4 / 4 | Duck | Duck |
| 02 | GPT-6 Astra | 3 / 5 / 2 | 4 / 4 / 3 | Duck | Duck |

Decision help favored Duck in all four reviewer-pair judgments; clarity favored Duck three times and tied once; Off was never preferred. Coverage favored Off in every judgment: the Off replies were longer and listed more peripheral gaps.

Both reviewers found factual slips on both sides. Off: "protection only works for complete snapshots" (a partial inside the grace period is protected too), and in pair 2 the claim that an interrupted deletion makes the next prune remove one more snapshot. Duck: "exactly at the grace period is kept" (it only escapes the stale rule), "only tests call list_state" (nothing does), and one over-general "protection never works for partials". GPT-6 caught three of these that Fable had missed. None of the replies' test runs or blocked probes were independently re-executed by the reviewers.

## What this does and does not show

Two pairs on one synthetic task, one model. The length and usage differences are consistent in direction with the job-recovery slice. Both reviewers preferring the Duck reply for decision help is a judgment about these four replies, not a general readability or correctness claim. The fixture author also acted as one reviewer, which is disclosed in the review file.
