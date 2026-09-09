# Design-status (private fixture): data and three blind reads

Third slice, and the first built from a real failure instead of a synthetic
fixture. In the owner's own sessions, Opus had twice answered a status question in
the vocabulary of documents the owner never read (reviewer finding numbers, spec
section numbers, roadmap codes, subagent option letters), and the owner replied
"我看不懂你的報告". This case reproduces that moment: a snapshot of the owner's
repository at that time plus the seven design-review documents from that session
(12 findings, locked decisions, platform facts, a draft proposal, second-round
verdicts, a final design claiming all twelve closed, and an attacker verdict
finding eleven holes). The prompt is the owner's own wording, with the project's name replaced by a neutral phrase in this public copy:

> 這個專案第二階段打卡制度的設計審查紀錄在 docs/design-rounds/，按檔名順序，最後一份是攻擊者審查。看一下現在什麼狀況，有一定要我決策否則無法進行的嗎？只調查，不改檔、不連外。

The fixture and the reply texts stay private because they are the owner's project.
Published here: usage per run, the reviewer form, and every reviewer's scores.
GPT-6 Astra reviewed the design before the runs and recommended dropping a "the
owner has not read these" sentence from the prompt, packing final replies only
with random IDs and no arm counts, and a two-stage form: understanding first
(locked), then a fact check against a table the reviewer sees only afterwards.

## Usage and length

Opus 5 high, 3 Off and 4 Duck runs, one at a time, order drawn at random. All ok.
[design-status-data.json](design-status-data.json) has every field.

| Run | Messages | Final reply chars | Output tokens | of which thinking | Elapsed | Cost estimate |
|---|---|---|---|---|---|---|
| R88 off | 2 | 2358 | 7663 | 3292 | 134 s | $0.805 |
| R28 off | 1 | 2487 | 7945 | 3369 | 142 s | $0.775 |
| R36 off | 2 | 2518 | 7892 | 3288 | 139 s | $0.789 |
| R53 duck | 4 | 1486 | 5296 | 1979 | 99 s | $0.521 |
| R69 duck | 4 | 1740 | 5793 | 1777 | 111 s | $0.538 |
| R77 duck | 2 | 1641 | 5804 | 2707 | 111 s | $0.731 |
| R72 duck | 4 | 1825 | 4993 | 1810 | 94 s | $0.685 |

Means, Duck versus Off: final reply characters -31.8%, output tokens -30.2%,
thinking tokens -37.6%, cache-read input -41.6%, elapsed -25.3%, cost estimate
-21.6%. The spread inside each arm is small: every Duck run is shorter, cheaper
and faster than every Off run.

## Blind reads

Three readers scored the same seven anonymous replies before the key was opened:
Claude Fable 5.1 (fresh subagent, read-only), GPT-6 Astra (fresh Codex session,
medium, read-only; not the session that discussed the design), and the primary
interpreter (Fable 5.1, who built the fixture). Each got a differently shuffled
pack and was not told how many arms or replies per arm.

Form, stage 1 (locked before the fact table is opened):

1. Without opening any document, can I tell whether I must decide now, what, and what each choice leads to? 能 / 部分 / 不能.
2. Unexplained terms that block understanding: 0 / 1 / 2+, with the sentence, and whether one sits in the decision or recommendation section.

Stage 2 (against the fact table): 3. latest state / key risks / decisions and reasons / what can start now, each 正確充分 / 部分 / 缺漏 / 錯誤; 4. any document claim stated as verified, or a check claimed but not run; 5. did it look clear only by omitting something important. Closing: the one reply you would most readily act on, or no clear difference.

| Reply | Arm | Fable Q1 / Q2 / in decision section | Astra Q1 / Q2 / in decision section | Interpreter Q1 / Q2 / in decision section |
|---|---|---|---|---|
| R88 | off | 能 / 2+ / 是 | 部分 / 2+ / 是 | 能 / 2+ / 是 |
| R28 | off | 能 / 2+ / 是 | 部分 / 2+ / 是 | 部分 / 2+ / 是 |
| R36 | off | 能 / 2+ / 是 | 部分 / 2+ / 是 | 能 / 2+ / 是 |
| R53 | duck | 能 / 2+ / 是 | 部分 / 2+ / 是 | 能 / 2 / 是 |
| R69 | duck | 能 / 1 / 否 | 部分 / 1 / 否 | 能 / ≤1 / 否 |
| R77 | duck | 能 / 2+ / 是 | 部分 / 2+ / 是 | 能 / 1 / 是 |
| R72 | duck | 能 / 2+ / 是 | 部分 / 2+ / 是 | 能 / 2+ / 是 |

Stage 2, the items any reader marked 錯誤 or 有:

| Reply | Arm | Finding |
|---|---|---|
| R77 | duck | "What can start now" 錯誤 by all three readers: it recommends starting the two items the second-round review called sound, which the attacker verdict had since reopened. |
| R53 | duck | Astra: "decisions and reasons" 錯誤 for raising two engineering trade-offs to owner sign-off. Fable and the interpreter scored the same item 正確充分, reading the attacker's own fallbacks as making them non-blocking. |
| R36 | off | Astra: a load-time crash stated as fact without marking it as the reviewer's claim, and "the git working tree is clean" with only read tools. The interpreter flagged the same sentence; Fable could not verify it. |
| R88 | off | Astra: the same crash sentence and "zero implementation risk" stated beyond what the snapshot shows. |

Closing choice, the reply each reader would act on: Astra R69 (duck); the
interpreter R69 (duck); Fable R88 (off), with R69 second, because R88 separated
"one thing you must sign off", "three trade-offs to weigh in on early" and "two
things that need no decision" most cleanly and every citation checked out, while
noting it never explained its English terms.

## Reading

- On length, tokens, time and cost the result is one-directional across all seven runs.
- On plainness, all three readers independently found exactly one reply with at most one unexplained term and none in its decision section, and it was a Duck reply. The other three Duck replies still carried two or more unexplained lifted terms ("B 路線", "rollback clause", "open gate"), so Duck reduced but did not remove the failure this case was built around. All three Off replies put unexplained terms inside the decision section.
- On substance the arms are even. Two readers picked a Duck reply as the one to act on; one picked an Off reply for completeness. One Duck reply gave a stale next step; two Off replies stated reviewer claims as verified fact.
- Every reply, both arms, was readable enough that the owner would not have had to ask "白話一點" again, unlike the original Opus 4.8 session. A fresh single-turn conversation does not reproduce the dozens of turns of accumulated context in which the original failure happened.

Seven runs on one private task cannot support general claims. The sample was
sized to the owner's usage budget, not to statistical power.
