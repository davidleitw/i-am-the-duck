# Astra blind review

The reviewer read the common question, fixture, and all 14 complete visible replies before the key was opened. It rated clarity, required-information coverage, and faithfulness separately on an ordinal 1–5 scale. Code names, diagrams, and standard technical terms were allowed; shorter text was not automatically rewarded.

The reviewer was GPT-6 Astra in a separate agent from the primary interpreter. It had previously helped discuss the evaluation direction, but did not receive the response mapping, usage, or the primary agent's existing judgments for this pass. It did not independently execute the subject tools. See [the locked assessment](astra-review.json) and [complete replies](initial-responses.md).

| Pair | Model | A | B | Clarity preference | Decision-help preference |
|---|---|---|---|---|---|
| 01 | Opus 5 high | opus-three-arm-duck | opus-three-arm-off | Duck | Duck |
| 02 | Opus 5 high | opus-two-more-duck | opus-two-more-off | Tie | Off |
| 03 | Opus 5 high | opus-third-pair-duck | opus-third-pair-off | Off | Off |
| 04 | Luna max | job-recovery-duck | job-recovery-off | Off | Off |
| 05 | Luna max | job-recovery-three-more-r1-off | job-recovery-three-more-r1-duck | Duck | Duck |
| 06 | Luna max | job-recovery-three-more-r2-duck | job-recovery-three-more-r2-off | Tie | Tie |
| 07 | Luna max | job-recovery-three-more-r3-off | job-recovery-three-more-r3-duck | Tie | Duck |

Across these comparisons, clarity favored Duck twice, Off twice, and tied three times. Decision help favored each side three times and tied once. This does not support a claim that Astra generally found Duck cognitively better. It does support reporting shorter replies and lower Opus output usage separately from answer quality.

The main differences concerned missing conditions and overconfident diagnoses, not simply terminology or length. Findings apply to this question and these responses, not every coding task. Scores and preferences are judgments, not statistical proof.
