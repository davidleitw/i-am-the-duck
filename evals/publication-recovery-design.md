# Publication recovery: proposed evaluation

Status: fixture and baseline-only runner support validated. One Opus 5/xhigh off
run completed; all four principal incident answers were explicit and correct, so
the clarity gate was not met. The user subsequently requested one on run, which
also completed; paired execution measurements are recorded at
`.evals-local/publication-recovery-opus5-xhigh-pair-20260908/record.md`.
Full baseline assessment:
`.evals-local/publication-recovery-opus5-xhigh-baseline-20260908/baseline-assessment.md`.
The design and answer key below were fixed before the run; this status is post-run.
Designed by the main agent. This document and its answer key must never be
copied into a subject workspace.

## What this tests

Can an explanation let a maintainer predict which report readers see after
overlapping publication attempts and interrupted writes? The previous retention
case primarily combines classification rules and deletion recovery. This case
requires tracking two workers, two durable stores, and a separate reader pointer
through time. Complexity must come from those interactions, not obscure names,
large amounts of code, or misleading prose.

An uploaded object, a local receipt, and a reader-visible publication are distinct
facts. A good response must connect them to consequences in the supplied incidents.
Naming all three without explaining the incidents is insufficient.

## Proposed subject prompt

> 我接手這個報表發布流程。使用者從固定入口讀報表，背景程式負責上傳新版並切換入口。值班同事看到「上傳成功」時，還不確定能不能告訴使用者新版已經可讀。
>
> 請依程式、測試與操作文件，說明從要求發布到讀者看到新版的完整過程，尤其是中斷、重試與兩個 worker 先後處理同一份工作時會怎樣。
>
> 請判斷下面四次事件。每次事件都獨立從「入口指向第 6 版、要求發布第 7 版，尚無第 7 版的上傳結果」開始。時間是測試用的秒數；請把執行步驟當成給定的順序，不必猜測其他未列出的操作。
>
> 1. A 在第 0 秒領到工作，上傳成功，卻在記下結果前中斷。第 31 秒 B 接手並完成流程。中斷後和 B 完成後，讀者各看到哪一版？上傳呼叫會重做嗎？會多出一份檔案嗎？
> 2. A 在第 0 秒領到工作後停住。第 30 秒 B 接手，但還沒上傳；A 隨後恢復，先把自己的流程走完，接著 B 才繼續。A 還能上傳嗎？能切換入口嗎？最後由誰讓新版可讀？
> 3. A 已上傳第 7 版，且記下結果，還沒切換入口。此時有人要求發布第 8 版。A 繼續處理，之後第 8 版的工作在上傳前失敗，沒有其他操作。讀者會看到哪一版？第 7 版上傳成功對這個判斷有什麼影響？
> 4. A 在第 0 秒領到工作，上傳並記下結果後中斷。第 31 秒只重新啟動服務，尚未執行背景掃描；之後才執行一次背景掃描並讓它完成。這兩個時間點，讀者各看到哪一版？要由哪一步收尾？
>
> 最後請告訴值班同事，要查哪些資料，才能分辨「檔案已存在」、「這次工作可以繼續」和「使用者已讀得到新版」。請區分程式可推得的行為、測試實際驗證的範圍，以及這個本機案例無法證明的事情。可依 README 執行測試。只調查，不修改程式、不連外，也不擴大成架構審查。

Pre-run author clarifications in the executable case: scenario 2's steps after
B claims all happen at time 30; scenario 3's A finalizes before lease expiry and
the revision-8 worker stops before calling upload. The initial revision-6 object
is seeded in test setup. These fix unspecified timing and initial data without
changing the intended questions or expected outcomes.

The prompt deliberately does not request a diagram, a table, brevity, or any Duck
specific wording. Both arms receive exactly the same prompt.

## Fixture contract to implement

Use Python's standard library and two temporary SQLite databases. One stores jobs
and the current reader pointer; the other stands in for object storage. Separate
commits make the interruption window explicit. All time is supplied by callers.

- `catalog.py`: requested revision, active revision, immutable jobs, claim and
  completion transactions. A job contains revision, lease token, lease deadline,
  status, and optional receipt. The initial active revision is 6.
- `storage.py`: `put(report_id, revision)` returns the same object ID for the same
  immutable revision. Record every call separately from distinct stored objects.
  Two calls may therefore produce one object. No real network service is involved.
- `publisher.py`: `request`, `claim`, `deliver`, `scan_once`, and `read_current`.
  The public path must be fully traceable; no unused alternate recovery mechanism.
- `test_publication.py`: deterministic baseline tests, including ordinary
  publication, storage deduplication, lease boundary, and explicit scan recovery.
- `README.md`: entry points, local scope, and `python3 -B -m unittest -v`.
  `OPERATIONS.md`: operational observations only; no embedded answer key and no
  deliberately false promise that restarting automatically performs recovery.

Target about 300–450 lines including fixture tests. No cache, cleanup, retry
budget, pause switch, real threads, or generic provider interface is needed.

### Required semantics

1. `request` inserts an immutable job and sets the requested revision atomically.
   It does not move the active pointer. Revisions increase; a duplicate request
   reuses its job. An older outstanding job is not silently deleted.
2. `claim` acquires queued work or reclaims running work when `now >= lease_until`.
   The lease lasts 30 seconds. Every claim increments the job's token. The token
   identifies which claim may save a receipt or finalize the job.
3. `deliver` uses its claim snapshot. Without a saved receipt it calls `put`, then
   tries to persist the returned receipt. A stale worker can therefore still call
   storage. Receipt writes require the current token and an unexpired lease;
   rejection stops that worker before finalization.
4. A claim that already has a receipt skips `put`. Finalization atomically checks
   token, unexpired lease, and requested revision. If the revision is still wanted,
   it updates the active pointer and marks the job done in one transaction. With a
   valid claim but an obsolete revision it marks the job superseded and leaves the
   active pointer untouched. There is no fallback to the last uploaded revision.
5. Process startup only opens stores. `scan_once` explicitly claims recoverable
   work and calls `deliver`. Recovery with a persisted receipt uses the new token;
   recovery without one calls storage again. `read_current` uses the active pointer,
   never the latest object or the requested revision.

```text
request -> claim -> deliver
                     | saved receipt? yes -----------------+
                     | no                                  |
                     v                                     |
                    put -> save receipt -------------------+
                              | stale/expired: stop        |
                                                           v
                                                        finalize
                                              stale/expired | stop
                                              obsolete      | superseded
                                              current       | active + done

read_current -> active revision
startup -> open stores; scan_once must be invoked separately
```

The implementation must keep these writes transactional within each database,
but must not pretend there is a transaction spanning storage and the catalog.
Crash injection points sit after `put` and after saving the receipt. Tests use
explicit interleavings, not sleeps. In scenario 2 all work after B's claim occurs
at time 30, before B's lease expires.

## Private answer key and verification

Freeze these expectations before the baseline. Implement independent acceptance
tests outside the copied fixture for all four scenarios. The subject sees the
ordinary fixture tests, not these acceptance tests or this document. Report both
test sets separately so author validation is not confused with subject evidence.

| Incident | Required prediction | Explanation needed |
| --- | --- | --- |
| 1 | After crash: 6. After B: 7. Two put calls, one revision-7 object. | A's storage commit survives without a local receipt. B reclaims after expiry and repeats the same immutable storage key, then activates. |
| 2 | B may claim at exactly 30. A calls put but cannot save its receipt or activate. B then calls put and activates 7. Two calls, one object. | Token replacement rejects A; the lease does not prevent its storage call. B's earlier claim snapshot has no receipt. |
| 3 | Active stays 6; requested is 8; revision-7 object and receipt remain; job 7 becomes superseded. | Finalization checks the current requested revision. Failure of 8 does not activate 7 or roll back the request. |
| 4 | Restart alone: 6. After successful scan: 7; only one put call in total. | Opening stores does no recovery. Scan reclaims and resumes from the persisted receipt. |

Operational checklist must separate storage lookup, job receipt/status/token and
deadline, requested revision, and active pointer. A receipt alone proves neither
current authority nor reader visibility. Passing local tests cannot establish a
real provider's idempotency, multi-process reliability, or power-loss durability.

Reject or repair the fixture before running if a required answer depends on an
unspecified ordering, or if the implementation disagrees with this contract.
Once the baseline starts, do not edit this case for the Duck arm.

## Baseline gate and paired evaluation

Requested subject: Claude Code `claude-opus-5`, effort `xhigh`, once off, then once
on if the baseline gate supports proceeding. No paid call has yet verified this
model/effort combination. Preserve a selection failure; do not downgrade or retry.

The runner accepts xhigh and passes it to Claude. The preparation change adds
`--arm off` to select only baseline; omitting it retains the original pair.
A later on run must use the same frozen case, fixture, and plugin snapshot.
Preserve hashes, isolation, and provider evidence; do not add a resume framework.

Before viewing the baseline, fix these review questions:

- Can a reader answer each incident using only the response, without opening code?
  Record each answer as explicit, derivable, missing, or wrong, with a quotation.
- Does the response explain why repeating a call differs from duplicating an
  object, and why upload success differs from visibility? Point to the actual
  explanation rather than counting terms or diagrams.
- Are claims about tests, blocked tools, and the storage stand-in faithful to
  the recorded evidence? Assess correctness separately from clarity.

Proceed as an exploratory clarity comparison when the baseline is substantially
correct but leaves at least two incident decisions missing or requiring the reader
to reconstruct an unexplained condition. One wrong central result is a correctness
failure, not sufficient evidence of poor explainability. If every decision is clear
and correct, report no demonstrated clarity headroom and stop before on. Borderline
cases need an explicit judgment; do not force an aggregate score to pass the gate.

This baseline gate is knowingly unblinded and selects for a weak baseline. Keep
that selection visible in any result; one selected pair cannot establish general
discrimination or an average Duck improvement. Do not keep sampling baselines.

If on proceeds, randomize the saved pair and give the complete anonymous responses
to fresh Claude Fable 5.1 and GPT-6 Astra reviewers at medium effort, following the
existing eval skill. Save their judgments before opening their key. The coordinator
has already seen off and cannot claim to be blind. Reviewers may infer the arm from
style; anonymization does not guarantee blinding.

Retain full progress/final messages, observed model, requested effort and whatever
effort evidence the CLI emits, hooks, test invocations/results, denials, workspace
changes, usage, time, and raw cost fields. Requested effort is not proof of observed
effort when the provider does not report it. Length, tokens, and cost are secondary
measurements and never the criterion for understanding.
