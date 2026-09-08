# Initial visible responses

All assistant-visible messages are retained in order.

## opus-three-arm-off (anthropic / claude-opus-5 / high / off)

### Message 1

I'll start by exploring the repository structure to find the files you mentioned.

### Message 2

Small, self-contained codebase. Let me read all of it.

### Message 3

Now let me run the tests as the README specifies, and check whether a worker loop exists anywhere.

### Message 4

All 8 tests pass, and there is no loop/daemon anywhere in the code. Let me probe the behaviors the tests don't cover, in a temp dir (no repo changes).

### Message 5

The heredoc invocation was denied by the current permission mode. Let me try a simpler form.

### Message 6

我已讀完全部五個檔案並跑過測試（8 個全過）。有兩個補充實測被權限模式擋下（下方「被略過的驗證」有說明），那幾項只能以讀碼推論，我會標示清楚。

---

## 一、任務的完整生命週期

```
submit ──> queued ──claim_ready──> running ──┬─ 成功 ─> record_effect ─> done
  │                    ↑                     ├─ Retryable 且 attempt < max ─> queued（available_at = now + retry_delay）
  │                    │                     ├─ Retryable 且 attempt >= max ─> failed
  │                    │                     ├─ Permanent ────────────────────> failed
  │                    │                     └─ 其他任何例外 ─────────────────> failed
  │                    │
  └────── resubmit（人工，僅限 running / failed）──────────────────────────────┘
```

關鍵細節：

- **設定在提交當下就凍結**。`store.py:71-72` 把 `max_attempts` 與 `retry_delay` 寫進該筆 job 的資料列。事後改 `config.py` 不影響已提交的任務。
- **attempt 在領取時就 +1**（`store.py:100`），所以第一次執行時 `attempt == 1`。因此 `max_attempts` 是**總執行次數**，不是「額外重試次數」。
- **成功路徑是兩次獨立的 commit**：`record_effect`（`store.py:160`）先寫，`mark_done`（`store.py:185`）後寫。這個縫隙是後面所有重複執行問題的根源。

## 二、重試由誰觸發、什麼時候停止

**由 worker 自己觸發，而且沒有任何排程器。** 重試就是 `worker.py:44` 呼叫 `queue_retry`，把狀態改回 `queued` 並把 `available_at` 推到未來（`store.py:124`，固定延遲，**沒有指數退避、沒有 jitter**）。

這裡有個必須先講清楚的事實：**整個 repo 沒有任何迴圈、sleep、thread 或常駐程序**（我 grep 過 `while|loop|sleep|daemon|Thread|schedul`，零命中）。`run_once` 顧名思義只處理一個任務就返回。所以「自動重試」的實際意思是：**必須有外部呼叫者持續呼叫 `run_once()`，而且要在 `available_at` 過了之後呼叫**。這個呼叫者不在這份程式碼裡。

停止重試的條件：

| 例外類型 | 行為 | 位置 |
|---|---|---|
| `RetryableJobError` 且 `attempt < max_attempts` | 重排隊，等 `retry_delay` | `worker.py:44` |
| `RetryableJobError` 且 `attempt >= max_attempts` | 終結為 `failed` | `worker.py:41-43` |
| `PermanentJobError` | 立刻 `failed`，不重試 | `worker.py:46-49` |
| **其他任何例外**（TypeError、連線錯誤等） | 立刻 `failed`，**不重試** | `worker.py:50-53` |

最後一列是營運上最容易誤判的地方：只有明確拋出 `RetryableJobError` 才會重試。任何沒被包裝的程式錯誤或第三方套件例外，都會被記成 `unexpected error: ...` 並**一次就終結**。

`failed` 是絕對終點——`claim_ready` 只選 `state = 'queued'`（`store.py:88`），失敗的任務永遠不會被自己撿回來。

## 三、程式重新啟動後，未完成的任務會怎樣

- **`queued` 的任務**：資料在 SQLite，重啟後只要有人再呼叫 `claim_ready` 就會被領取。📖（讀碼確認；測試沒有專門的「queued 跨重啟」案例）
- **`running` 的任務**：**永遠不會自動恢復**。沒有 lease、沒有 heartbeat、沒有 visibility timeout，也沒有啟動時把 `running` 掃回 `queued` 的邏輯。`claim_ready` 只看 `queued`。

✅ 這點測試明確驗證了：`test_restart_does_not_reclaim_running_job`（`test_job_flow.py:114-123`）重建 `JobStore` 後斷言 `claim_ready()` 回傳 `None`，只有人工 `resubmit` 才能解開。

也就是說：**重啟這個動作本身，正好會製造出唯一一種無法自動恢復的狀態。**

## 四、人工重送會不會造成重複執行

**會，而且這是已被測試確認的行為，不是理論風險。**

機制：崩潰發生在 `record_effect` 與 `mark_done` 之間 → 效果已經寫入，任務停在 `running` → 人工 `resubmit` → 重跑 → **產生第二筆效果紀錄**。

✅ `test_crash_after_effect_leaves_running_and_can_duplicate_effect`（`test_job_flow.py:101-112`）直接斷言效果數從 1 變成 2。測試名稱裡的 `can_duplicate_effect` 就是在講這件事。

**現有機制有沒有處理？完全沒有。**

- `effects` 表（`store.py:47-53`）只有 `effect_id INTEGER PRIMARY KEY AUTOINCREMENT`，**沒有任何 UNIQUE 約束**，`record_effect` 是無條件 INSERT。
- 沒有 idempotency key、沒有去重邏輯。
- 更麻煩的是：`resubmit` 把 `attempt` 重設為 0（`store.py:143`），下次領取又變回 1，所以**重複的那筆效果紀錄帶著跟原本一樣的 attempt 編號**，只能靠 `created_at` / `effect_id` 區分。📖（讀碼確認；測試只斷言筆數，沒斷言 attempt 值）
- 唯一存在的去重槓桿是呼叫端自己給穩定的 `job_id`，靠 PRIMARY KEY 擋掉重複提交——但 `store.py:62` 預設是 `uuid4()`，等於預設不去重。

**另一個測試沒覆蓋的風險**：`resubmit` 允許對 `running` 的任務操作，但**不會取消真正還在執行的那一次**。如果任務其實還活著（不是崩潰），重送會在它執行中把它重新排隊，可能被併發領取跑第二次；而原本那個 worker 收尾時會撞上 `WHERE state = 'running'` 的守衛而拋 `ValueError`（`store.py:127`、`store.py:184`）。測試裡所有 `resubmit` 都是對「已經停止執行」的任務做的，這個併發情境**未被測試**。而且從資料庫上，`running`「還活著」和「已崩潰」是**無法區分的**。

## 五、文件與程式不一致：哪些說法不能直接採信

`RUNBOOK.md` 三條步驟，兩條有問題：

| RUNBOOK 說法 | 實際情況 |
|---|---|
| `:5` 「提交任務後啟動 worker；若執行失敗，失敗會自動重試」 | **不能採信**。(a) 沒有可「啟動」的常駐 worker，只有 `run_once`；(b) 只有 `RetryableJobError` 會重試，永久錯誤與所有未分類例外都是一次終結 |
| `:6` 「worker 重啟後會繼續處理尚未完成的任務」 | **不能採信**。對 `queued` 為真，對 `running` 為假，且測試明確反證 |
| `:7` 「任務仍失敗時，可由人工重送」 | 事實正確，但**漏掉最關鍵的一句**：重送會重複產生效果，且沒有任何防重複機制 |

反過來，`README.md:15` 寫的「worker.py：領取、**執行一次**、分類錯誤與寫入完成狀態」是準確的，而且正好和 RUNBOOK 的「啟動 worker」框架互相矛盾。**兩份文件衝突時，以 README 為準。**

## 六、任務失敗時的判斷依據

先做一次前提檢查：**確認到底有沒有東西在持續呼叫 `run_once`**。如果沒有，「等待」這個選項在所有情況下都不成立。

| 觀察到的狀態 | 判斷 | 動作 |
|---|---|---|
| `queued`，`available_at` 在未來 | 重試已排程 | **等待**（前提是 driver 活著） |
| `queued`，`available_at` 已過但沒被領取 | 不是任務問題，是沒有 driver | **調查**呼叫端 / 程序是否存活 |
| `failed`，`last_error` 以 `unexpected error:` 開頭 | 程式 bug 被當成永久失敗 | **先調查**，直接重送多半會再失敗 |
| `failed`，永久錯誤（如 payload 無效） | 輸入本身有問題 | **先修 payload/目的地再重送**，否則只是再燒一輪 attempt |
| `failed`，`attempt == max_attempts` 的可重試錯誤 | 上游持續故障 | 確認上游恢復後**重送** |
| `running`，確認沒有活著的 worker | 卡死，不會自動恢復 | **重送，但先查 `effects_for(job_id)`**；已有效果紀錄就代表這次重送會產生重複 |
| `running`，worker 可能還活著 | **不要重送**（會並行執行） | 從程序監控判斷，資料庫本身無法分辨 |

注意 `resubmit` 會把 `attempt` 重設為 0，等於**發還一整輪完整的重試額度**。

## 七、範圍區分

**程式已實作**：狀態機、attempt 在領取時遞增、三類錯誤分流、固定延遲重排隊、`failed`/`running` 都不會被自動領回、`resubmit` 僅限 `running`/`failed` 且重設 attempt、`claim_ready` 用 `BEGIN IMMEDIATE` + `WHERE state='queued'` 做原子領取。

**測試實際確認的範圍**（8 個案例，全部單程序 + 假時鐘 + 暫存目錄）：成功路徑、重試延遲與到達上限後失敗、上限前恢復、永久失敗不重試、**重啟不會撿回 running**、**崩潰後重送會產生重複效果**、重送 failed/running 的狀態與 payload。

**測試沒有覆蓋的**：`except Exception` 這條分支（未分類例外）完全沒有測試；`queued` 跨重啟；多程序併發領取；對「真的還在執行中」的任務重送。

**仍然不知道的**：

1. 生產環境誰呼叫 `run_once`、多久一次、單一還是多程序——repo 裡沒有進入點。這決定了「等待」是否有意義。
2. `effects` 對應的真實外部效果是什麼、本身是否冪等。`README.md:3` 說它只是本機 stand-in。若真實效果是寄信或扣款，重複就是實質傷害；若上游本身冪等，風險就低很多。**這是決定「重送前要多小心」的關鍵，我無法從這份程式碼得知。**
3. 沒有 lease/heartbeat，無法從資料區分「執行中」與「已崩潰」；你們是否有其他訊號（程序監控、log）可用，未知。
4. 併發安全性：`claim_ready` 的寫法看起來是原子的，但完全沒有併發測試，且 `store.py:28-30` 只設了 `foreign_keys`，**沒有設 WAL 或 busy_timeout**，高併發下可能出現 `database is locked`。未驗證。

**被略過的驗證**：我原本要在暫存目錄跑一段腳本，實測四件事——未分類例外確實不重試、重複的兩筆 effect 其 attempt 是否都是 1、`queued` 任務跨重啟仍可領取、`resubmit` 對 `queued`/`done` 的行為。兩次嘗試都被 Bash 權限模式拒絕（只有 `python3 -B -m unittest` 被放行）。這四項目前只有讀碼推論，未實際執行；若要我補做，需要放行在暫存目錄執行 python 腳本的權限。

我沒有修改任何程式或文件。

## opus-three-arm-duck (anthropic / claude-opus-5 / high / duck)

### Message 1

I'll start by finding the files you named and reading the whole path a task takes.

### Message 2

我讀完了四個檔案與測試，並跑過本機測試（8 個全過）。有一個想額外驗證的情境被權限擋下，我在下面標明了哪一條因此只是讀碼推論。

## 結論先講

**這套程式沒有任何東西會自己重試。** `worker.py` 裡沒有迴圈、沒有排程、沒有背景執行緒；`run_once` 領一個任務、跑一次、回傳就結束。所謂「重試」只是把任務改回 `queued` 並把 `available_at` 設成 `now + retry_delay`，之後必須有人（或外部迴圈）再呼叫一次 `run_once`，它才會真的被再執行。測試裡也是手動一次次呼叫 `run_once`。

所以 `RUNBOOK.md` 那三行操作筆記，**兩行不能直接採信**。

## 一個任務的完整路徑

```
submit()                       state=queued, attempt=0
   |                           max_attempts / retry_delay 在此刻由 JobConfig 複製進資料列
   v
claim_ready(now)               只挑 state='queued' 且 available_at <= now
   |                           進入交易，state=running，attempt += 1
   v
operation(job)
   |
   +-- RetryableJobError ----> attempt >= max_attempts ?
   |                              是 -> mark_failed()   終止，不再重試
   |                              否 -> queue_retry()   state=queued
   |                                                    available_at = now + retry_delay
   |
   +-- PermanentJobError -----> mark_failed()           終止
   |
   +-- 其他任何例外 ----------> mark_failed()           終止（訊息前綴 unexpected error）
   |
   +-- 成功 ------------------> record_effect()  先寫效果
                                mark_done()      再寫完成
                                ^^^ 這兩步之間若行程中斷，任務會永遠卡在 running
```

重試在 `worker.py:41` 停止：`job.attempt >= job.max_attempts`。因為 `attempt` 是在領取時就加一，預設 `max_attempts=3` 代表總共執行 3 次（第 1、2 次排重試，第 3 次判定失敗）。延遲是固定值，沒有退避也沒有抖動。設定在 submit 當下就寫進該筆資料，改 `config.py` 不會影響已送出的任務。

## 重啟之後，未完成的任務會怎樣

`claim_ready` 的查詢條件只有 `state = 'queued'`。停在 `running` 的任務不會被任何查詢撿回來——程式裡沒有租約、沒有逾時、沒有清掃程序，`updated_at` 有寫入但沒有任何地方讀它。

意思是：**重啟只救得回「已排入佇列」的任務；當機當下正在執行的那一筆，永遠不會自己回來。** 而那一筆正是重啟時最需要處理的。`test_restart_does_not_reclaim_running_job` 直接確認了這件事——關掉 store、重新開啟後 `claim_ready()` 回傳 `None`，必須人工 `resubmit` 才動得了。`failed` 的任務同樣是終點，不會自動再跑。

## 人工重送會不會重複執行：會，而且沒有任何防護

有兩條路徑：

**一、當機後重送（測試已確認）。** 成功路徑是先 `record_effect` 再 `mark_done`。若在這兩次寫入之間行程停止，效果紀錄已經留下、任務卻還是 `running`。人工重送後再跑一次，就會產生第二筆效果。測試 `test_crash_after_effect_leaves_running_and_can_duplicate_effect` 就是在確認這個結果——它斷言重送後效果從 1 筆變成 2 筆。測試名稱裡的 `can_duplicate_effect` 是把重複當成既有行為記錄下來，不是把它當成 bug。

**二、對還活著的 worker 重送（讀碼推論，未實測）。** `resubmit` 接受 `running` 狀態的任務（`store.py:138`）。操作者無法從資料庫分辨「當機卡住」和「還在跑」——兩者都只是 `state='running'`，沒有心跳也沒有時間戳被檢查。如果對一個仍在執行的任務重送，就會有兩份執行重疊。而 `mark_done` / `queue_retry` / `mark_failed` 的保護條件只有 `state = 'running'`，不檢查是哪一次嘗試，所以舊的那份執行完成時仍然寫得進去。我原本想跑一段臨時腳本實際驗證這條，但執行被權限擋下，因此這一條目前只是程式碼推論，不是跑出來的結果。

去重機制完全不存在：`effects` 是純附加表，主鍵是自動遞增流水號，沒有對 job_id 的唯一約束，`record_effect` 之前也沒有任何檢查，payload 裡沒有冪等鍵。另外 `resubmit` 會把 `attempt` 歸零，所以效果紀錄裡的 attempt 編號在重送後會重複出現，只能靠 `created_at` 分辨是哪一輪。

## 文件哪裡不能採信

| RUNBOOK 的說法 | 實際 |
|---|---|
| 「若執行失敗，失敗會自動重試」 | 只有 `RetryableJobError` 會被排回佇列，而且沒有東西會自動去跑它。`PermanentJobError` 和其他任何未預期例外都是一次就終止。 |
| 「worker 重啟後會繼續處理尚未完成的任務」 | 只對 `queued` 成立。當機時停在 `running` 的任務永遠不會被重新領取。 |
| 「任務仍失敗時，可由人工重送」 | 動作本身可行，但沒提重送可能重複產生已經發生過的效果，而程式對此沒有任何防護。 |

`README.md` 的檔案分工和「effects 只是本機 stand-in」的說明與程式一致，可以採信。

## 測試實際確認到哪裡

8 個測試涵蓋：成功路徑（attempt=1、一筆效果）、重試延遲的精確時間點與到達上限後轉 failed 且無效果、重試中途恢復、永久錯誤不重試、當機後卡在 running 且重送會重複、重啟不重領 running、重送 failed 會保留 payload 並把 attempt 歸零、重送 running 會回到佇列並從第 1 次重新開始。

**沒有測到的**：任何併發情境（`claim_ready` 用 `BEGIN IMMEDIATE` 看起來有防重複領取，但完全沒測；連線也沒設 `busy_timeout`，多行程同時寫入可能直接拿到 database is locked）；重送與存活中的 worker 競爭；「未預期例外 → failed」這條分支；`JobConfig` 的預設值（測試每次都明確指定）。

**仍然不知道的**：程式裡沒有依狀態列出任務的方法，`get` 需要 job_id，所以維運上要怎麼找出卡住的 `running` 任務，這份程式沒有答案；還有最關鍵的一點——這是 fixture，`effects` 只是替身，真實那個副作用本身是否冪等，決定了重送到底安不安全，而這份程式回答不了。

## 遇到失敗時怎麼判斷

**可以等**：狀態是 `queued`、`available_at` 還在未來、`attempt < max_attempts`，**而且你已經確認確實有東西在持續呼叫 `run_once`**。這個前提在目前這份程式裡不成立，所以先確認你們的部署是怎麼驅動 worker 的；如果沒有外部迴圈，等多久都不會動。

**一定要人處理**：狀態是 `running` 但沒有存活的 worker（當機遺留），這種永遠不會自己恢復；狀態是 `failed`，這是終點。

**重送之前一定要先查兩件事**：一是 `effects_for(job_id)` 看效果是否已經產生過——因為沒有去重，重送就是再做一次；二是確認原本的 worker 真的死了，否則會變成兩份同時跑。

**該調查而不是重送**：`last_error` 顯示是永久錯誤或 unexpected error 前綴的，重送只會用同樣方式再失敗一次，除非你確定原因是外部的、已經排除。

如果你要我補上其中一項驗證（例如實際跑一次重送與存活 worker 競爭的情境），我需要執行臨時腳本的權限；目前那次嘗試被擋下了。

## opus-two-more-off (anthropic / claude-opus-5 / high / off)

### Message 1

I'll start by exploring the repository structure to find the relevant files.

### Message 2

Small, self-contained codebase. Let me read everything.

### Message 3

Let me run the test suite and probe a few specific behaviors.

### Message 4

8/8 pass, and there's no loop, scheduler, lease, or reaper anywhere in the code. Let me probe the specific edge cases that the tests don't cover, using a throwaway script outside the repo.

### Message 5

The heredoc write was blocked. Let me use the file-writing tool instead and run the probe.

### Message 6

I have what I need from the code and the passing test run. Two ad-hoc probe scripts were blocked by permissions (only the README test command is allowed), so I've marked below which claims are code-reading only versus test-verified.

# 背景任務流程調查

## 1. 一個任務的完整生命週期

```
submit()          state=queued, attempt=0, available_at=now
                  max_attempts / retry_delay 從 JobConfig 複製進該列
   │
claim_ready(now)  WHERE state='queued' AND available_at <= now
                  → state=running, attempt = attempt + 1      ← attempt 在「領取」時遞增
   │
operation(job)    worker.run_once() 只呼叫一次
   ├─ RetryableJobError → attempt >= max_attempts ? mark_failed : queue_retry(available_at = now + retry_delay)
   ├─ PermanentJobError → mark_failed（不重試）
   ├─ 其他 Exception    → mark_failed（不重試，訊息前綴 "unexpected error: "）
   └─ 成功 → record_effect()  ← commit #1
             mark_done()      ← commit #2（兩次獨立 commit）
```

關鍵細節：`attempt` 在 `claim_ready` 遞增（`store.py:100`），不是在失敗時。所以 `max_attempts` 等於**總執行次數**，不是「重試次數」。`max_attempts=3` → 執行 3 次（第 1、2 次重排，第 3 次失敗）。

## 2. 重試由誰觸發 —— 這是最重要的一點

**沒有任何東西會自動觸發重試。**

`queue_retry`（`store.py:116-128`）只做一件事：把該列改回 `queued` 並把 `available_at` 推到 `now + retry_delay`。它不喚醒任何人。`worker.run_once()` 是**單次**呼叫：領一個任務、執行一次、寫狀態、返回。

`worker.py` 裡沒有迴圈、沒有執行緒、沒有排程器。我對整個 repo 搜尋 `while|sleep|Thread|schedul|daemon|loop|reaper|lease|timeout` —— **零命中**。測試裡的「重試」全都是測試自己再呼叫一次 `worker.run_once()`。

所以 RUNBOOK 說的「失敗會自動重試」，成立的前提是**外部有一個 driver 在反覆呼叫 `run_once()`**，而這個 driver 不在這個 repo 裡。接手時第一件要查清楚的事就是：正式環境裡是誰在驅動 `run_once()`、多久一次。這直接決定「等待」是否真的有意義。

## 3. 重試何時停止

- 只有 `RetryableJobError` 會重排。`PermanentJobError` 和任何未預期的例外都直接 `failed`，一次都不重試（`worker.py:46-53`）。
- 停止條件在 `worker.py:41`：`job.attempt >= job.max_attempts` 時改為 `mark_failed`。
- `retry_delay` 是**固定常數**，沒有指數退避、沒有 jitter。
- `max_attempts` / `retry_delay` 在 submit 當下就寫進該列，之後改 `config.py` 的預設值**不影響已存在的任務**。

測試 `test_retryable_failure_waits_for_delay_then_fails_at_limit` 完整驗證了這條路徑（`max_attempts=2`：t=1000 失敗→ `available_at=1010`；t=1009 領不到；t=1010 領到並判定 failed）。

## 4. 程式重啟後，未完成的任務會怎樣

**卡在 `running` 的任務永遠不會自己恢復。**

`claim_ready` 的 WHERE 條件只有 `state='queued'`（`store.py:88`）。schema 裡沒有 lease、沒有 visibility timeout、沒有 `claimed_at`，也沒有任何 reaper。`updated_at` 有寫入但**沒有任何程式碼讀它**。

這正是測試 `test_restart_does_not_reclaim_running_job` 明確斷言的行為：重開 DB 後 `claim_ready()` 回傳 `None`，必須人工 `resubmit()` 才能繼續。

→ **RUNBOOK 第 2 點「worker 重啟後會繼續處理尚未完成的任務」是錯的**，而且錯在最關鍵的情境：重啟本身就會製造 `running` 孤兒任務，而這正是唯一不會被續處理的狀態。只有 `queued` 的任務會被續處理。

## 5. 人工重送會不會重複執行 —— 會，而且沒有任何機制擋

風險來自 `record_effect` 和 `mark_done` 是**兩次獨立 commit**（`store.py:160` 與 `store.py:185`）。在兩者之間停止，效果已經持久化，但狀態仍是 `running`。

`resubmit()` 允許 `running` 和 `failed` 兩種狀態，把 `attempt` 歸零、清掉 `last_error`（`store.py:133-149`），**完全不檢查是否已經產生過效果**。

現有的防重複機制：**沒有**。
- `effects` 表只有 `effect_id INTEGER PRIMARY KEY AUTOINCREMENT`，`(job_id, attempt)` 上沒有 UNIQUE，payload 也沒有 idempotency key。
- `record_effect` 是無條件 INSERT。

測試 `test_crash_after_effect_leaves_running_and_can_duplicate_effect` 不只沒有防止這件事，而是**把它當成既定行為斷言下來**：crash → resubmit → 執行 → `effects` 有 2 筆。

另外兩個可從程式碼直接讀出、但**測試完全沒有涵蓋**的問題（這兩點是純程式碼推論，我沒能實際跑腳本驗證）：

- **對「真的還在跑」的任務 resubmit**：`resubmit` 把列改成 `queued`；若另一個 worker 接手，列又變回 `running`；此時**原本那個 worker** 的 `mark_done()`（條件是 `WHERE state='running'`）會匹配成功，於是把「第二次執行還在進行中」的任務標成 done。若還沒有人接手，原 worker 的 `mark_done()` 則會拋出未被捕捉的 `ValueError("job is not running")`。兩條路徑都沒有測試。
- **重送次數無上限**：`resubmit` 把 `attempt` 歸零但不動 `max_attempts`，也沒有任何重送計數，人工可以無限重送。

## 6. 文件與程式不一致 —— 哪些說法不能直接採信

`RUNBOOK.md` 三點裡有三點需要修正：

| RUNBOOK 說法 | 實際狀況 |
|---|---|
| 1. 「若執行失敗，失敗會自動重試」 | 只有 `RetryableJobError` 會重排；Permanent 與未預期例外一次都不重試。且 repo 內**沒有任何東西**會自動再驅動 `run_once()` |
| 2. 「worker 重啟後會繼續處理尚未完成的任務」 | **不成立**。`running` 的任務永遠不會被重新領取，必須人工介入。被 `test_restart_does_not_reclaim_running_job` 直接推翻 |
| 3. 「任務仍失敗時，可由人工重送」 | 技術上可行，但隱瞞了重送會重複已產生的效果，而這件事測試裡有明確示範 |

`README.md` 則是準確的 —— 它誠實標明 `effects` 只是本機 stand-in、不是生產設計，檔案分工描述也與程式相符。

**結論：RUNBOOK 三點都不能直接採信，第 2 點尤其危險，因為它會讓人在該人工介入時選擇等待。** 程式與測試是可信的事實來源。

## 7. 任務失敗時的判斷依據

先讀該列的 `state` / `attempt` / `max_attempts` / `available_at` / `last_error`，再對照 `effects_for(job_id)`：

**可以等**
- `state='queued'` 且 `available_at` 在未來且 `attempt < max_attempts` —— 但**前提是你已確認有 driver 在呼叫 `run_once()`**。這個前提在本 repo 內無法成立，必須先查清。

**需要人處理（不會自己恢復）**
- `state='running'` 且沒有活著的 worker → 永久卡住，等再久都不會動。
- `state='failed'` → 不會被重新領取（`test_permanent_failure_is_failed_without_retry` 已驗證）。

**重送前必做的檢查**
1. 先看 `effects_for(job_id)`：若當前 attempt 已有效果紀錄，重送就是重複執行一次外部效果。系統不會幫你擋。
2. 確認沒有 worker 仍持有這個任務，否則會踩到第 5 節的 `mark_done` 錯配問題。

**區分失敗原因的可用線索**（`last_error` 只存 `str(exc)`，不存例外型別）
- `last_error` 以 `"unexpected error: "` 開頭 → 是未預期例外，屬程式缺陷，重送通常無效。
- `attempt == max_attempts` → **可能**是重試耗盡。
- `attempt < max_attempts` 卻是 `failed` → 一定是 `PermanentJobError` 或未預期例外，**不修根因就重送沒有意義**。

這是目前唯一能區分「重試耗盡」與「永久失敗」的方法，因為兩者寫進 `last_error` 的格式完全相同。

## 8. 三層可信度區分

**程式已實作、可從程式碼確定**
狀態機與各轉移的 SQL 條件、attempt 在領取時遞增、三類例外的分流、固定延遲無退避、retry 政策在 submit 時凍結、`claim_ready` 只看 `queued`、無 lease/reaper、`effects` 無唯一鍵、`resubmit` 只接受 `running`/`failed` 且不重設政策也無次數上限。

**測試實際確認的範圍**（8 個測試全數通過）
成功路徑、重試等待延遲並在上限失敗、上限前恢復、永久失敗不重試、重啟不重領 running、resubmit 保留 payload 並重設 attempt、**以及重送會產生重複效果**。

**目前仍不知道的部分**
- 正式環境由誰、以什麼頻率驅動 `run_once()` —— repo 內完全沒有 entrypoint 或 driver。這是最大的空白。
- 併發行為：`BEGIN IMMEDIATE`（`store.py:83`）暗示了多程序意圖，但**沒有任何併發測試**，也沒有測試讓兩個 worker 碰同一個任務。第 5 節那兩個 `mark_done` 錯配情境屬於此類未驗證推論。
- 真實 `operation()` 是否具備冪等性 —— fixture 裡的 `local_operation` 是純函式，實際操作未知。
- 未被任何測試涵蓋：`JobConfig` 的驗證邏輯（`config.py:11-15`）、`config.py` 的預設值、對 `queued`/`done` 狀態呼叫 `resubmit`、以 `submit()` 重複 job_id。

## 說明

我沒有修改任何程式、沒有啟動外部服務，調查範圍限於這段任務流程。測試以 README 指定的 `python3 -B -m unittest -v` 執行，8 項全數通過。我另外嘗試在 `/tmp` 跑兩個一次性探測腳本（想實測 mid-flight resubmit 的 `mark_done` 行為、重送次數上限與效果去重），兩次都被權限設定擋下，因此第 5 節結尾那兩點僅來自程式碼閱讀、未經實際執行驗證 —— 若你希望我實測，需要放行執行臨時腳本的權限。

## opus-two-more-duck (anthropic / claude-opus-5 / high / duck)

### Message 1

I'll start by looking at the repository layout and the files you named.

### Message 2

8 個測試全部通過。以下是調查結果。

## 先講結論

**任務失敗後不會有任何東西自己去重試。** 程式裡沒有迴圈、沒有排程器、沒有背景執行緒 — 我搜尋整個目錄，找不到任何 while 迴圈、sleep、lease、timeout 或去重機制。`worker.py` 的 `run_once` 每次呼叫只處理一個任務就回傳。所謂「自動重試」，實際上只是把任務改回 `queued` 並設定一個可以再次領取的時間點，真正再跑一次要靠外面有人（或某個你還沒接手到的排程）持續呼叫 `run_once`。

## 一個任務的完整路徑

```
submit()  →  state=queued, attempt=0, available_at=now
                    |
                    v
            claim_ready(now)
            只挑 state='queued' 且 available_at <= now
            挑中就 state=running, attempt +1
                    |
                    v
              operation(job)
        ┌───────────┼───────────┬──────────────┐
        │           │           │              │
     成功      RetryableJobError │        其他任何例外
        │           │      PermanentJobError    │
        v           v           v              v
  record_effect  attempt        mark_failed   mark_failed
  → mark_done    >= max?        (不重試)      (不重試)
     state=done  ├ 是 → mark_failed
                 └ 否 → queue_retry
                        state=queued
                        available_at = now + retry_delay
```

## 重試由誰觸發、什麼時候停

- **只有 `RetryableJobError` 會被排回佇列。** `store.py:116` 的 `queue_retry` 把狀態改回 `queued`，可領取時間設為 `now + retry_delay` — 固定延遲，沒有指數退避、沒有抖動。
- **停止條件是 `job.attempt >= job.max_attempts`**（`worker.py:41`）。因為 attempt 是在領取當下就 +1，所以 `max_attempts=3` 代表總共執行 3 次，第 3 次失敗就進 `failed`。測試用 `max_attempts=2` 驗證了這個算法。
- **`PermanentJobError` 直接 `failed`，不重試** — 這是設計意圖。
- **但這裡有個你會踩到的坑：任何其他例外也直接 `failed`，同樣不重試**（`worker.py:50-53`）。也就是說，一個沒有被包成 `RetryableJobError` 的連線逾時、暫時性 DB 錯誤，會被當成永久失敗處理掉。任務進 `failed` 不代表問題是永久性的，只代表拋出的例外型別不是 `RetryableJobError`。
- 次數與延遲是**提交當下**從 `JobConfig` 抄進該筆任務的（`store.py:71-72`）。之後改 `config.py` 不會影響已經在佇列裡的任務。

## 程式重啟後，未完成的任務會怎樣

分兩種，差別很大：

- **停在 `queued` 的**：重啟後正常被領取，沒有問題。
- **停在 `running` 的：永遠不會再被碰。** `claim_ready` 的 SQL 只查 `state = 'queued'`（`store.py:88`）。沒有租約到期、沒有心跳、沒有回收機制，所以進程在執行到一半時掛掉，那筆任務就永久卡在 `running`，不會超時、不會自己回來。`test_restart_does_not_reclaim_running_job` 就是在驗證這件事：重新開啟 store 之後 `claim_ready()` 回傳 `None`，必須人工 `resubmit` 才會動。

**卡在 `running` 的任務是等不到的，只能人工介入。**

## 人工重送會不會重複執行

會，而且測試明確確認了這件事。

`resubmit`（`store.py:133`）允許 `running` 或 `failed` 的任務被重排，把 attempt 歸零、清掉 `last_error`。但 `effects` 表的寫入（`record_effect`）是無條件 INSERT，沒有任何唯一鍵、沒有 idempotency key、沒有「這個任務已經產生過效果」的檢查。`test_crash_after_effect_leaves_running_and_can_duplicate_effect` 就演了完整的情境：任務在寫完效果之後、標記完成之前中斷 → 狀態停在 `running`，效果紀錄有 1 筆 → 人工 resubmit 後重跑成功 → 效果紀錄變成 2 筆。

**所以現有機制不但沒有處理重複執行，這個測試是刻意把重複執行當成既定行為記錄下來的。**

還有一個更麻煩的情況，程式讀得出來但沒有測試涵蓋：因為沒有租約，store 無法分辨「`running` 是因為有 worker 正在跑」還是「`running` 是因為進程死了」。如果人工去 resubmit 一個其實還活著的任務，就會有兩份同時在跑；而 `_update_running` 只檢查 `state = 'running'`、不檢查 attempt，所以舊那份跑完的 `mark_done` 會把新那份標成完成。這是我從程式推論的，不是測出來的。

另外 `resubmit` 會清掉 `last_error`，重送之前想保留失敗原因的話要先自己記下來。

## 文件哪裡不能直接採信

`RUNBOOK.md` 三句話裡有兩句與程式不符：

| RUNBOOK 說法 | 實際狀況 |
|---|---|
| 「若執行失敗，失敗會自動重試」 | **不能採信。** 只有 `RetryableJobError` 會排回佇列，而且排回去之後還要有人再呼叫 `run_once` 才會真的跑。永久錯誤和未預期例外完全不重試。 |
| 「worker 重啟後會繼續處理尚未完成的任務」 | **不能採信。** 只對停在 `queued` 的成立。停在 `running` 的永遠不會被重新領取，這正是測試驗證的行為。 |
| 「任務仍失敗時，可由人工重送」 | 屬實，但漏了最重要的一句：重送可能造成效果重複執行，而且系統不會擋。 |

`README.md` 的描述我沒有找到與程式衝突的地方。

## 三個層次分開講

**程式已經實作的**：一次領取一個任務、領取時 attempt +1、三種錯誤分類、固定延遲重排、達到上限轉 `failed`、`running`/`failed` 可人工重送並歸零 attempt、效果紀錄與任務狀態分開兩張表寫入。

**測試實際確認的**：成功路徑只執行一次；重試要等滿延遲才會被領取，未到時間 `run_once` 回 `None`；達上限轉 `failed`；重試中途成功則效果只有一筆；永久失敗不重試；中斷後停在 `running` 且重送會產生第二筆效果；重啟不會回收 `running`；重送保留原 payload 並把 attempt 歸零。全部在單一進程、單一 worker、手動時鐘下跑。

**目前仍不知道的**：
- 誰在正式環境負責重複呼叫 `run_once`，用什麼間隔 — 這個 repo 裡完全沒有，你需要去外面找。
- 多個 worker 同時跑會怎樣。`claim_ready` 用了 `BEGIN IMMEDIATE`，看起來是為併發領取設計的，但沒有任何併發測試，SQLite 跨進程的實際行為未經驗證。
- 上面提到的「resubmit 撞上還活著的 worker」是否真的會造成狀態錯亂 — 從程式推論會，但沒測過。
- `failed` 之後有沒有告警或監控，任務卡在 `running` 有沒有人會發現。

## 遇到失敗時怎麼判斷

**可以等**：任務狀態是 `queued` 且 `available_at` 還在未來 — 這是正常的重試等待，前提是你已經確認有東西在持續呼叫 `run_once`。查一下 `attempt` 和 `max_attempts` 就知道還剩幾次機會。

**要人工重送**：任務停在 `running` 且沒有 worker 正在跑它。這種不會自己恢復。**但重送之前先查 `effects_for(job_id)`** — 如果已經有紀錄，代表效果已經產生過，重送會做第二次；這時要先確認這個操作重做一遍是否安全。

**要先調查再決定**：任務是 `failed`，因為 `failed` 混了三種完全不同的原因。看 `last_error` 的內容：開頭是 `unexpected error:` 的，表示例外沒有被歸類，問題可能其實是暫時性的、值得重送；如果 `attempt` 等於 `max_attempts`，是重試耗盡；其餘就是明確的永久錯誤，重送多半只會再失敗一次，該去修 payload 或下游。

**要往上報**：確認不到有沒有 worker 在跑、或是同一批任務大量卡在 `running` — 那不是單筆任務的問題，是執行端沒有在動或反覆崩潰。

我沒有修改任何程式，也沒有啟動外部服務；只讀了你列的檔案並跑了 README 裡的本機測試。

## opus-third-pair-off (anthropic / claude-opus-5 / high / off)

### Message 1

I'll start by exploring the repository structure and reading the key files.

### Message 2

A small, self-contained system. Let me read all six files.

### Message 3

Now let me run the test suite and check exactly which code paths it exercises.

### Message 4

All 8 pass. Let me check whether anything actually drives the worker in a loop, then empirically verify the resubmit-while-running scenario.

### Message 5

No scheduler, no loop, no `__main__` entry point outside the tests — `run_once` is only ever called by the test file. Let me empirically verify the resubmit-while-actually-running scenario.

### Message 6

Heredoc file-writing is blocked. Let me run the probe inline instead — read-only, no repo changes.

### Message 7

我讀完了全部六個檔案、跑過測試（8/8 通過），並確認了呼叫關係。有一件事先說明：我想跑一段 ad-hoc 腳本去實測「重送時原 worker 仍在執行」的交錯情況，但這個 session 的權限只允許 README 裡的測試指令，ad-hoc `python3 -c` 被擋下了。所以下面關於併發交錯的部分是**純讀碼推導、未經實測**，我會標明。

---

# 一、任務的完整生命週期

```
submit()          → state=queued, attempt=0, available_at=now
                    max_attempts / retry_delay 在此刻寫進該筆 row
   ↓
claim_ready()     → BEGIN IMMEDIATE，選 state='queued' AND available_at<=now
                    → state=running, attempt +=1
   ↓
operation(job)    ← 由外部注入的 callable（repo 內沒有任何真實實作）
   ├─ 正常回傳      → record_effect() → mark_done()  → done
   ├─ RetryableJobError
   │     ├─ attempt >= max_attempts → mark_failed()  → failed（終局）
   │     └─ 否則                     → queue_retry() → queued, available_at=now+retry_delay
   ├─ PermanentJobError → mark_failed() → failed（終局，不重試）
   └─ 其他任何 Exception → mark_failed() → failed（終局，不重試）
```

關鍵：`store.py:88` 的 `WHERE state = 'queued'` 是整個恢復邏輯的樞紐——**只有 `queued` 會被領取**。

# 二、重試由誰觸發、什麼時候停止

**由誰觸發：沒有任何東西自動觸發。** `worker.py:32` 的 `run_once()` 只處理一件任務就返回。我搜過整個 repo，沒有 while 迴圈、沒有 sleep、沒有 thread、沒有排程器，也沒有 `__main__` 進入點——`run_once` 的唯一呼叫者是 `test_job_flow.py`。

所以「自動重試」實際只代表**把 row 改回 `queued` 並設定 `available_at`**。真正的重新執行，必須有人（或某個此 repo 尚未提供的驅動程式）在延遲時間之後再呼叫一次 `run_once`。

**什麼時候停止：** `worker.py:41` 的 `if job.attempt >= job.max_attempts`。`attempt` 是 `claim_ready` 遞增後的值，所以 `max_attempts=3` = 總共執行 3 次（1 次初始 + 2 次重試）。停止條件有三種：

| 錯誤型別 | 行為 |
|---|---|
| `RetryableJobError` | 重排；達 `max_attempts` 才 `failed` |
| `PermanentJobError` | 立刻 `failed`，一次都不重試 |
| **其他所有例外** | 立刻 `failed`，一次都不重試（`worker.py:50-53`） |

第三列值得注意：未分類的例外（含程式 bug、網路層拋出的原生錯誤）被當成**永久失敗**，不是重試。這是設計選擇，不是 bug，但它決定了「暫時性故障若沒被包成 `RetryableJobError`，就永遠不會自動重試」。

補充兩點會影響「該等多久」：`retry_delay` 是**固定值，無指數退避、無 jitter**（`config.py:9`）；而且 `queue_retry` 收到的 `now` 是**領取時間**而非完成時間（`worker.py:34` 取得 now 後一路傳下去），所以任務跑得比 `retry_delay` 久時，重試其實是立即可領的。

# 三、程式重啟後，未完成的任務會怎樣

**停在 `running` 的任務永遠不會被自動撿回。** `claim_ready` 只看 `queued`，而系統裡**沒有 lease、沒有 heartbeat、沒有 owner 欄位、沒有 running 逾時回收**。worker 在 `claim_ready` 之後、終局寫入之前中止，該筆 row 就永久卡在 `running`，只能靠人工 `resubmit()` 救回。

這一點測試直接證實了：`test_restart_does_not_reclaim_running_job`（`test_job_flow.py:114-123`）關掉 store、用同一個 DB 重新開啟，`claim_ready()` 回傳 `None`，必須呼叫 `resubmit` 才能繼續。

同時要注意一個操作面的死角：`Job` dataclass 沒有把 `updated_at` 曝露出來（`store.py:187-198`，該欄位存在於資料表但未進入 `_job()`）。也就是說，**操作者無法從 Job API 判斷一筆 `running` 的任務是「worker 還在跑」還是「worker 已經死了」**——而這正是決定「等」還是「重送」所需要的資訊。

# 四、人工重送會不會重複執行？有沒有機制處理？

**會重複，而且系統完全沒有處理。**

`record_effect`（`store.py:151`）是無條件 INSERT，`effects` 表沒有任何唯一鍵（`store.py:47-53`：只有 autoincrement 主鍵，`job_id` 甚至沒有宣告 FOREIGN KEY）。沒有 idempotency key、沒有去重、沒有「這個效果已產生」的檢查。

最明確的證據是**測試自己就把重複執行寫成預期行為**：`test_crash_after_effect_leaves_running_and_can_duplicate_effect`（`test_job_flow.py:101-112`）——crash 後 effects 有 1 筆，`resubmit` 再跑一次之後變成 2 筆，測試 assert 的就是 `2`。

更糟的是 `resubmit` 會把 `attempt` 重設為 0（`store.py:143`），所以重送後的第一次執行 attempt 又是 1。crash 情境下 effects 表會出現**兩筆 attempt 都等於 1 的紀錄**，`attempt` 因此無法充當事後對帳的去重鍵。

另外，`resubmit` 保留原本的 `max_attempts`，等於每次重送都發一份全新的完整重試額度，而且**重送次數沒有上限、沒有計數欄位**。

**未經實測的推導**：`resubmit` 允許對 `running` 的任務執行（`store.py:138`）。若原 worker 其實還活著，`_update_running` 的守衛只有 `WHERE state='running'`，**沒有比對 attempt 或 owner**，因此無法分辨是哪一次執行寫回來的。讀碼上會出現這種交錯：A 仍在跑 → 操作者 resubmit → B 領走並開始跑 → A 完成並呼叫 `mark_done`，此時 state 確實是 `running`（B 的），rowcount=1，**A 會成功把 B 正在執行中的任務標成 done**，隨後 B 收尾時才拋 `ValueError("job is not running")`。這條路徑我沒能實測，請當成待驗證的疑慮而非結論。

# 五、文件與程式不一致：哪一句不能採信

`RUNBOOK.md` 三個步驟，一個錯、兩個具誤導性；`README.md` 我沒找到與程式不符之處。

**最不能直接採信的是第 2 句：「worker 重啟後會繼續處理尚未完成的任務。」**

這句與程式**直接相反**。重啟後 `running` 的任務不但不會被繼續處理，而且是永久停滯。若照這句話操作，遇到 worker 崩潰時會選擇「重啟並等待」，結果就是任務無聲卡死、沒有任何告警。`claim_ready` 的 SQL 與 `test_restart_does_not_reclaim_running_job` 兩者都否證它。

另外兩句要加上但書：

- 第 1 句「啟動 worker；若執行失敗，失敗會自動重試」：**沒有可以「啟動」的 worker**（無迴圈、無進入點），而且「失敗會自動重試」只對 `RetryableJobError` 成立——永久錯誤與未分類錯誤都是一次就終局。這句話涵蓋範圍過廣。
- 第 3 句「可由人工重送」：機制存在，但完全沒提重送會**從頭重跑並重複產生效果**，而這是測試已明文確認的行為。

# 六、任務失敗時的判斷依據

先看 `state`，這是唯一可靠的分流依據：

**`state='queued'` 且 `available_at` 在未來 → 可以等**（前提是確實有人會再呼叫 `run_once`；目前 repo 內沒有這個東西）。查 `last_error` 確認是暫時性原因。預期還會再跑 `max_attempts - attempt` 次。

**`state='failed'` → 不會自動恢復，需要人處理。** 這是終局狀態，`claim_ready` 永遠不會再碰它（`test_permanent_failure_is_failed_without_retry` 已確認）。決定重送前必須先確認：這次失敗是在 `record_effect` **之前**還是之後？查 `effects_for(job_id)`——若已有效果紀錄，重送就會產生第二份。

**`state='running'` → 最需要謹慎，且資訊不足。** 它可能是「還在跑」也可能是「worker 已死」，而系統沒給你分辨的手段。重送前務必用外部方式（process 是否存活、log）確認原 worker 確實已停止；若原 worker 還活著，依讀碼推導會造成雙重執行與狀態互相覆寫。

**重送前的通用檢查**：`effects_for(job_id)` 是否已有紀錄 → 有的話重送必然重複，需先確認該效果可否重複承受。

**需要進一步調查而非直接重送的情況**：`last_error` 以 `"unexpected error: "` 開頭（表示例外未被分類，可能是程式 bug 而非外部故障，重送大機率同樣失敗）；或同一 job 反覆被重送仍失敗——由於 `resubmit` 重設 attempt 且無重送計數，這種迴圈不會自己停下來。

# 七、三種確定程度

**程式已實作、讀碼可確認**：狀態機與四種轉移；`attempt >= max_attempts` 的停止條件；`claim_ready` 只取 `queued`；`BEGIN IMMEDIATE` 的領取交易；`resubmit` 限 `running`/`failed` 且重設 attempt、保留原重試設定；`record_effect` 無去重；重試延遲固定無退避；設定在 submit 當下寫入該筆 row（**改 `config.py` 不影響已提交的任務**）。

**測試實際確認的範圍**（8 個測試全過）：成功路徑與 effect 寫入；重試延遲的邊界（1009 不可領、1010 可領）；達上限轉 `failed` 且無 effect；重試後成功恢復；永久失敗不重試；**重啟不回收 `running`**；**重送會產生重複效果**；重送 failed/running 後 payload 保留、attempt 重設。

**目前仍不知道 / 測試未涵蓋**：
- `worker.py:50-53` 的未分類例外分支**沒有任何測試**（`SimulatedCrash` 是在 try 區塊**之外**拋出的，走的是傳播路徑，不是這個 except）。
- **併發完全未測**：全部測試單執行緒、單一 sqlite connection。`BEGIN IMMEDIATE` 的互斥性、兩個 worker 同時領取、以及第四節那條 A/B 交錯路徑，都未被驗證——我也因權限限制未能實測。
- `config.py` 的 `__post_init__` 驗證（`max_attempts<1`、bool、負的 `retry_delay`）**零測試覆蓋**。
- 各種 `ValueError`/`KeyError` 防線未測：對 queued/done 任務 resubmit、對不存在的 job resubmit、非 running 狀態下 mark_done/queue_retry。
- 多任務排序（`ORDER BY created_at, job_id`）未測；`max_attempts=1`、`retry_delay=0` 等邊界未測。
- **最大的未知**：`operation` 是注入的 callable，repo 內**沒有任何真實實作**。哪些真實故障會被歸類成 retryable、哪些是 permanent，完全取決於未來接上去的那段程式，這份 fixture 無法回答。這也意味著第六節的決策樹，其分流品質最終取決於錯誤分類做得對不對。

如果要我接著做，我會建議優先補的是 `running` 的 lease/heartbeat（讓重啟能安全回收）與 effect 的 idempotency key（讓重送安全），並修正 `RUNBOOK.md` 第 2 句——但你只要我調查，所以我沒有動任何程式。

## opus-third-pair-duck (anthropic / claude-opus-5 / high / duck)

### Message 1

I'll start by looking at the files you named.

### Message 2

我讀完四個程式檔、測試與兩份文件，並跑了 README 指定的測試（8 個全數通過）。以下是結果。

## 先講結論

**這套系統沒有任何自動恢復機制在「程式重啟」之後生效。** 只有一種失敗會自己回到佇列等下一次執行：`worker.py` 收到 `RetryableJobError` 且嘗試次數還沒用完。其他所有情況——永久錯誤、非預期例外、以及在寫入效果之後、標記完成之前中斷——都不會自己動，必須人介入。

而人工重送目前**確實會造成重複的外部效果**，程式沒有任何防護，測試反而是明確把這件事記錄下來的。

## 一個任務的完整路徑

```
submit()  state=queued, attempt=0, available_at=now
   |
   v
claim_ready(now)  ── 找不到 state=queued 且 available_at<=now 的任務 ──> 回傳 None（worker 空轉）
   |  找到 → state=running, attempt+1（同一個 IMMEDIATE 交易內完成）
   v
operation(job)
   |
   +-- 成功 --> record_effect()  ← 效果寫入這裡
   |              |
   |              +-- 中途中斷 --> 停在 state=running，效果已寫入，永遠不會被再領取
   |              |
   |              v
   |            mark_done()  state=done（終點）
   |
   +-- RetryableJobError
   |       |
   |       +-- attempt >= max_attempts --> mark_failed()  state=failed（終點）
   |       |
   |       +-- 還有次數 --> queue_retry()  state=queued, available_at = now + retry_delay
   |                                          |
   |                                          +--> 等下一次有人呼叫 run_once()
   |
   +-- PermanentJobError --> mark_failed()  state=failed（終點）
   |
   +-- 其他任何 Exception --> mark_failed()  state=failed（終點，不重試）
```

## 重試由誰觸發、什麼時候停止

**觸發者不是程式自己。** `queue_retry` 只做一件事：把狀態改回 `queued`，並把 `available_at` 設成 `now + retry_delay`。真正要讓任務再跑一次，必須有人再呼叫一次 `run_once`。而整個專案裡 `run_once` 只在測試中被呼叫過——沒有迴圈、沒有排程器、沒有 `__main__` 進入點、沒有常駐程序。所以「自動重試」的自動，指的是「不需要人改狀態」，不是「不需要人再跑一次」。

**停止條件**在 `worker.py:41`：`job.attempt >= job.max_attempts` 就轉成 `failed`。因為 `attempt` 是在領取時就加一的，`max_attempts=3` 代表總共執行三次（不是三次重試）。延遲是固定值，沒有指數退避。

還有一點對排查很重要：`max_attempts` 和 `retry_delay` 是在 `submit` 當下寫進該筆資料的（`config.py` 的註解也是這樣寫的）。改 `config.py` 不會影響已經在佇列裡的任務。

## 程式重新啟動後，未完成的任務

**留在 `running` 的任務永遠不會被撿回來。** `claim_ready` 的查詢條件只有 `state = 'queued'`，而程式裡沒有租約、沒有心跳、沒有 running 逾時回收（我搜過 lease/timeout/heartbeat，完全沒有）。`test_restart_does_not_reclaim_running_job` 就是在確認這件事：重開 store 之後 `claim_ready()` 回傳 `None`，必須呼叫 `resubmit` 才動得了。

所以中斷的任務會有兩種殘留：狀態卡在 `running`，而效果可能已經寫進去、也可能還沒——從資料庫上看不出來是哪一種，只能去查 `effects` 表有沒有對應的列。

## 人工重送與重複執行

會重複，而且沒有任何機制在處理。

`record_effect` 是無條件 INSERT，`effects` 表只有自增主鍵，沒有 (job_id, attempt) 唯一鍵、沒有冪等鍵、沒有「這次執行是否已產生效果」的檢查。`resubmit` 把 `attempt` 歸零，所以重送後的執行會用 attempt=1 再寫一列新的效果。

`test_crash_after_effect_leaves_running_and_can_duplicate_effect` 直接把這個結果寫死在斷言裡：中斷後效果有 1 列，`resubmit` 再跑一次之後變成 2 列。這是測試確認過的行為，不是我的推測。

另外有一個測試沒有涵蓋、但從程式讀得出來的風險：`resubmit` 允許對 `running` 狀態的任務動手（`store.py:138`），而它無法判斷那個 worker 是不是還活著。如果原本的執行其實還在跑，重送會讓同一筆任務被第二個執行緒同時領走；接著先完成的那一方會呼叫 `mark_done`，把狀態變成 `done`，另一方再呼叫 `mark_done` 就會撞上 `ValueError("job is not running")`。測試都是單執行緒的，這條路徑沒有被驗證過。

`resubmit` 唯一擋住的是 `queued` 和 `done` 狀態，會直接丟 `ValueError`。

## 文件哪一句不能直接採信

`RUNBOOK.md` 三句話裡有兩句與程式不符：

- 第 1 句「提交任務後啟動 worker；若執行失敗，失敗會自動重試」——**部分不成立**。只有 `RetryableJobError` 會重排；永久錯誤和非預期例外一次就進 `failed`。而且「啟動 worker」在這個 repo 裡沒有對應的東西可以啟動。
- 第 2 句「worker 重啟後會繼續處理尚未完成的任務」——**不成立**，這是最危險的一句。重啟後卡在 `running` 的任務不會被繼續處理，測試明確證明相反。
- 第 3 句「任務仍失敗時可由人工重送」——成立，但漏掉了重送會重複產生效果這個代價。

`README.md` 的描述是準確的，它把 `worker.py` 寫成「領取、執行一次」，沒有宣稱有常駐迴圈。

## 遇到失敗時怎麼判斷

先查 `state`，再查 `effects` 表：

**可以等**：`state = queued` 且 `available_at` 還在未來。這是重試排程中，前提是確實有東西會再呼叫 `run_once`（在這個 repo 裡沒有，所以實務上要確認你們部署環境裡是誰在跑）。等到 `available_at` 之後再看一次。

**需要重送**：`state = failed`。這是終點，不會自己動。重送前先看 `last_error` 判斷是永久性問題（`PermanentJobError` 那類，例如 payload 不合法——重送只會再失敗一次）還是耗盡次數的暫時性問題（重送有意義）。也要先確認 `effects` 表有沒有已經產生的列，重送會再加一列。

**需要進一步調查**：`state = running` 但已經沒有 worker 在跑。這種情況要先確認兩件事才動手——效果是否已經產生（查 `effects_for`），以及有沒有可能還有活著的執行程序（因為 `resubmit` 不會幫你擋）。確認完再決定是重送、還是手動改成 `done`。

**特別注意**：`state = failed` 但 `effects` 表裡有對應的列。這代表效果已經產生但後續失敗了，重送等於做第二次。

## 三種確定程度

**程式已實作、我讀得到的**：三種錯誤分類與各自的去向；重試次數上限的判斷點與固定延遲；`claim_ready` 只看 `queued`；`resubmit` 會把 `attempt` 歸零因此重置重試預算；重試參數在提交時固定。

**測試實際確認的**：成功一次完成並寫入一列效果；重試延遲到期前領不到、到期後領得到、次數用完轉 `failed`；重試後恢復成功只寫一列效果；永久錯誤一次就 `failed`；重啟後不會撿回 `running`；中斷後重送會產生兩列效果；對 `failed` 和對 `running` 重送都能重新跑起來。八個測試我都跑過，全過。

**目前仍不知道的**：實際部署時是誰、以什麼頻率呼叫 `run_once`（repo 裡沒有這段）；多個 worker 或多個程序同時運作時的行為（測試全是單執行緒，`BEGIN IMMEDIATE` 的保護範圍沒有被驗證過）；對還活著的 worker 執行 `resubmit` 會發生什麼（我從程式推出上面那條競態路徑，但沒有測試涵蓋）；真實的外部效果是否本來就具備冪等性——`effects` 表只是本機替身，README 已經聲明它不是真實服務，所以「重複一列」在真實系統裡的代價有多大，要看實際接的是什麼。

我沒有修改任何程式，也沒有啟動外部服務。

## job-recovery-off (openai / gpt-5.6-luna / max / off)

### Message 1

我會只追查任務生命週期、重試、重啟恢復與人工重送的重複執行風險；先讀 `store.py`、`worker.py`、`config.py`、測試、`RUNBOOK.md`／`README.md`，再依 README 跑本機測試，最後把「程式實作」「測試確認」「尚未知悉」分開整理。不會修改檔案或啟動外部服務。

### Message 2

目前程式顯示幾個關鍵分歧：`RetryableJobError` 會依次數排程重試，永久／未預期例外直接終止；但「重啟後繼續處理尚未完成任務」與目前 `claim_ready` 的行為似乎不一致，且效果寫入與完成標記分兩次提交，可能留下重複效果。我先跑 README 指定測試，再核對每個狀態轉移與測試涵蓋範圍。

### Message 3

## 結論

只有「明確拋出 `RetryableJobError`、且尚未達到 `max_attempts`」的任務可以等待自動重試。永久錯誤、未預期例外、達到次數上限，以及 worker 重啟後遺留的 `running` 任務，都需要人工處理。

目前沒有內建的重複執行防護；人工重送確實可能造成重複效果。

## 任務生命週期

1. `submit()` 建立 `queued` 任務，`attempt=0`，並把提交時的 `max_attempts`、`retry_delay` 固定存入資料庫。[store.py](evals/fixtures/job-recovery/store.py:61)  
   預設值是最多 3 次、間隔 10 秒。[config.py](evals/fixtures/job-recovery/config.py:8)

2. `run_once()` 呼叫 `claim_ready()`，只會領取 `state='queued'` 且 `available_at <= now` 的任務，並將狀態改為 `running`、`attempt` 加一。[store.py](evals/fixtures/job-recovery/store.py:81)

3. 執行 `operation(job)`：[worker.py](evals/fixtures/job-recovery/worker.py:32)

   - 成功：先寫入 `effects`，再把任務標成 `done`。[worker.py](evals/fixtures/job-recovery/worker.py:55)
   - `RetryableJobError` 且尚未達上限：改回 `queued`，`available_at = 現在 + retry_delay`。[worker.py](evals/fixtures/job-recovery/worker.py:39)
   - `RetryableJobError` 且已達上限：改為 `failed`。[worker.py](evals/fixtures/job-recovery/worker.py:41)
   - `PermanentJobError`：立即 `failed`，不重試。
   - 其他 `Exception`：以 `unexpected error: ...` 記錄並立即 `failed`。[worker.py](evals/fixtures/job-recovery/worker.py:46)

`max_attempts` 包含第一次執行。例如 `max_attempts=3` 時，第一次、第二次失敗會重新排隊，第三次失敗後停止並變成 `failed`。

## 重試由誰觸發

第一次失敗的處理由 `JobWorker.run_once()` 觸發，它呼叫 `store.queue_retry()`。`JobStore` 只負責保存排程時間，程式中沒有獨立的計時器、輪詢迴圈或 supervisor。

因此「自動重試」實際上需要外部 worker 持續再次呼叫 `run_once()`。時間未到時，`claim_ready()` 會回傳 `None`；時間到了之後，下一次呼叫才會重新領取。

## 程式重啟後的行為

`claim_ready()` 只搜尋 `queued`，所以狀態會如下：

| 重啟時狀態 | 重啟後行為 |
|---|---|
| `queued` 且已到 `available_at` | 可被重新領取 |
| `queued` 但尚未到時間 | 保留，等時間到且再次輪詢 |
| `running` | 不會自動領回，會一直停在 `running` |
| `failed` | 不會自動重試 |
| `done` | 保持完成 |

測試直接確認了「重啟不會重新領取 `running` 任務」。[test_job_flow.py](evals/fixtures/job-recovery/test_job_flow.py:114)

尤其是成功流程分成兩次提交：先寫 `effects`，再寫 `done`。若在兩者之間崩潰，任務會是 `running`，但效果紀錄已存在。[worker.py](evals/fixtures/job-recovery/worker.py:55)

## 人工重送與重複執行

`resubmit()` 只接受 `running` 或 `failed`，會：

- 使用相同的 `job_id` 與 payload；
- 改回 `queued`；
- 將 `attempt` 重設為 0；
- 清除 `last_error`；
- 保留既有的 `effects` 紀錄。[store.py](evals/fixtures/job-recovery/store.py:133)

所以人工重送可能造成：

- 原 worker 其實仍在執行，重送後又被另一個 worker 領取；
- 原操作已產生效果但尚未標成完成，重送後再次產生效果；
- 既有 `effects` 表沒有依 `job_id` 或操作識別碼去重的限制，只有 `effect_id` 唯一鍵；
- `mark_done()` 等狀態更新只依 `job_id` 和 `state='running'`，沒有 attempt token 或 lease fencing，舊 worker 可能影響重送後的新執行週期。

測試明確確認：效果寫入後模擬崩潰，再重送會留下兩筆效果紀錄。[test_job_flow.py](evals/fixtures/job-recovery/test_job_flow.py:101)

因此現有機制是「記錄可能發生的效果」，不是「防止重複效果」。`README.md` 也明確說 `effects` 只是本機 stand-in，不是真實外部服務或生產設計。[README.md](evals/fixtures/job-recovery/README.md:3)

## 文件不能直接採信的地方

`RUNBOOK.md` 有兩個過度概括的說法：

- 「若執行失敗，失敗會自動重試」不能一概採信：只有 `RetryableJobError` 且未達上限才會重試；永久錯誤與未預期例外不會。[RUNBOOK.md](evals/fixtures/job-recovery/RUNBOOK.md:5)
- 「worker 重啟後會繼續處理尚未完成的任務」不能直接採信：`running` 不會被 reclaim，`failed` 也不會自動重試。[RUNBOOK.md](evals/fixtures/job-recovery/RUNBOOK.md:6)

「可人工重送」本身符合 `resubmit()` 的介面，但文件沒有說明只能處理 `running`／`failed`、會重設嘗試次數，也沒有警告重複執行風險。[RUNBOOK.md](evals/fixtures/job-recovery/RUNBOOK.md:7)

## 測試確認範圍

已依 README 執行：

```text
python3 -B -m unittest -v
Ran 8 tests ... OK
```

測試實際確認了：

- 成功會變成 `done` 並有一筆效果；
- retryable failure 會等待延遲；
- 可在達上限前恢復；
- 達上限後會 `failed`；
- permanent failure 不重試；
- 重啟不會 reclaim `running`；
- 重送會重設 attempt；
- 效果已寫入後崩潰再重送會產生兩筆效果。

## 目前仍不知道的部分

- 真正部署環境是否有持續呼叫 `run_once()` 的 worker loop；
- worker 重啟由誰負責，以及是否有外部清理 `running` 任務；
- `operation` 對真實外部系統是否具備冪等性；
- 操作在拋出錯誤前是否已經產生外部效果；
- 多 worker 並行重送、資料庫錯誤或其他崩潰時機的實際表現；
- 資料庫中的 `last_error` 只有文字，未保存錯誤類型，單靠資料列不一定能判斷失敗分類。

## 實務判斷

- `queued`、已知是 retryable failure、`available_at` 尚未到：等待；到期後應由下一次 worker poll 執行。
- `queued` 已到期卻長時間沒有被領取：調查 worker loop 或排程是否正常。
- `failed`：先看 `last_error`、當前 attempt 與執行紀錄；永久錯誤、未預期錯誤或已達上限時需要人處理。
- `running` 且原 worker 仍健康：先等待。
- `running` 但 worker 已重啟或疑似死亡：先調查是否已產生效果；確認原執行不會再完成、且操作可安全重跑後才人工重送。
- `effects_for(job_id)` 有紀錄：視為已存在「可能已產生效果」的證據；沒有紀錄也不能證明外部沒有效果，因為外部效果並未與本機紀錄原子化。

## job-recovery-duck (openai / gpt-5.6-luna / max / duck)

### Message 1

我會沿著任務生命週期讀取 `store.py`、`worker.py`、`config.py`、相關測試、`RUNBOOK.md` 與 `README.md`，再執行 README 指定的本機測試；只做讀取與驗證，不改檔、不啟動外部服務。最後我會把「程式實作」「測試真正覆蓋」「文件或行為仍不確定」分開，並整理成失敗時的等待、重送、調查判斷依據。

### Message 2

目前流程骨架已明確：提交時把重試上限與延遲寫進任務本身；worker 先原子領取、再依錯誤類型決定排回佇列或終止。值得特別核對的是「重啟後 running 任務」與「效果已寫入但完成狀態尚未寫入」這兩個崩潰窗口，因為它們直接影響是否會重複執行。接著我會跑 README 指定測試，並補看精確行號與測試覆蓋範圍。

### Message 3

測試已通過 8/8。它們實際確認了：可重試錯誤會按延遲再跑、達到上限後變成 `failed`；永久錯誤不重試；成功會記錄一次效果；重啟不會接回 `running`；人工重送同一 `job_id` 會重置計數，且崩潰在效果寫入後再重送會留下兩筆效果。這已足以確認至少存在「可能重複效果」的窗口；我會再做一次只讀狀態檢查，確保沒有測試副作用，然後整理判斷準則與文件落差。

### Message 4

結論：只有「仍是 `queued`、尚未到 `available_at`、且原本是可重試錯誤」的任務適合等待。`failed` 不會自動再試；重啟後的 `running` 也不會自動接回。人工重送可能重複執行，現有機制沒有真正的去重或冪等保護。

## 完整流程

```text
submit
  ↓
queued，attempt=0，available_at=現在
  ↓ run_once → claim_ready
running，attempt 加 1
  ├─ RetryableJobError 且尚未達上限 → queued，等待 retry_delay
  ├─ RetryableJobError 且已達上限 → failed
  ├─ PermanentJobError → failed
  ├─ 其他 Exception → failed
  └─ operation 成功 → 寫入 effects → mark_done
                         └─ 此間崩潰 → running + effect 已存在
```

- 提交時，每個任務會保存自己的 `max_attempts` 與 `retry_delay`；預設分別是 3 次與 10 秒。[`config.py:5`](<evals/fixtures/job-recovery/config.py:5>)、[`store.py:61`](<evals/fixtures/job-recovery/store.py:61>)
- `attempt` 是實際執行次數，不是失敗次數。`max_attempts=2` 代表最多執行兩次。
- 重試由 `worker.py` 捕捉 `RetryableJobError` 後呼叫 `queue_retry` 觸發；SQLite 不會自行啟動重試。下一次執行仍需要 worker 再次呼叫 `run_once`。[`worker.py:32`](<evals/fixtures/job-recovery/worker.py:32>)、[`worker.py:39`](<evals/fixtures/job-recovery/worker.py:39>)
- `PermanentJobError` 與其他一般例外會立即進入 `failed`，即使尚未達重試上限。[`worker.py:46`](<evals/fixtures/job-recovery/worker.py:46>)
- 成功時，效果紀錄先 commit，任務完成狀態後 commit。因此兩次寫入之間若程序崩潰，任務會保持 `running`，但效果已存在。[`worker.py:55`](<evals/fixtures/job-recovery/worker.py:55>)、[`store.py:151`](<evals/fixtures/job-recovery/store.py:151>)

## 重啟後的行為

`claim_ready` 只尋找 `state='queued'` 且已到 `available_at` 的任務。[`store.py:81`](<evals/fixtures/job-recovery/store.py:81>)

| 重啟時狀態 | 程式行為 |
|---|---|
| `queued` 且已到時間 | 可被新 worker 領取 |
| `queued` 但尚未到時間 | 留在佇列，等之後再次呼叫 `run_once` |
| `running` | 不會自動 reclaim，會一直保持 `running` |
| `failed` | 不會自動重試 |
| `done` | 不會再執行 |

測試直接確認了重啟不會接回 `running` 任務。[`test_job_flow.py:114`](<evals/fixtures/job-recovery/test_job_flow.py:114>)

## 人工重送與重複執行

`resubmit` 只允許 `running` 或 `failed`，會：

- 使用同一個 `job_id` 與原本 payload；
- 將 `attempt` 重設為 0；
- 立即改成 `queued`；
- 清除 `last_error`；
- 保留既有 `effects` 紀錄。

[`store.py:133`](<evals/fixtures/job-recovery/store.py:133>)

因此人工重送可能重複執行。測試模擬「效果已寫入、完成狀態尚未寫入」後重送，結果留下兩筆效果紀錄。[`test_job_flow.py:101`](<evals/fixtures/job-recovery/test_job_flow.py:101>)

目前沒有：

- `job_id + attempt` 的唯一限制；
- 效果去重；
- 冪等鍵或外部效果確認；
- worker lease、owner 或 attempt token。

所以若原 worker 其實仍在執行，直接重送 `running` 任務也可能與原執行重疊。這個並行情境未被測試，但可由 `resubmit` 及完成更新只檢查 `state='running'` 看出風險。

## 文件不能直接採信的地方

[`RUNBOOK.md:5`](<evals/fixtures/job-recovery/RUNBOOK.md:5>) 的「執行失敗會自動重試」過於寬泛：只有 `RetryableJobError` 且未達上限時成立；永久錯誤、未預期例外、達到上限都不會重試。

[`RUNBOOK.md:6`](<evals/fixtures/job-recovery/RUNBOOK.md:6>) 的「重啟後繼續處理尚未完成任務」不能照字面相信：只適用於可被領取的 `queued` 任務，不適用於 `running` 或 `failed`。

README 明確說 `effects` 只是本機 stand-in，不是真實外部服務。[`README.md:3`](<evals/fixtures/job-recovery/README.md:3>) 因此測試只能證明本機效果紀錄會重複，不能證明真實外部服務是否會去重。

## 測試確認與未知範圍

README 指定的 `python3 -B -m unittest -v` 已通過，8/8 測試成功。測試確認了重試延遲、達上限停止、永久錯誤不重試、成功流程、崩潰後效果重複、重啟不 reclaim，以及人工重送重設計數。

目前仍未由測試確認：

- 是否有常駐 worker 迴圈持續呼叫 `run_once`；
- 真實外部效果是否冪等；
- operation 已產生外部效果後又丟出例外的情況；
- 多 worker 或人工重送與原 worker 同時執行的競態；
- 程序在其他寫入窗口崩潰時的行為。

## 失敗時的判斷

- `queued` 且 `available_at` 尚未到：可等待；但要確認有 worker 會再次呼叫 `run_once`。
- `queued` 且已到 `available_at` 卻長時間未執行：調查 worker 是否存活或是否有輪詢機制。
- `failed`：先調查 `last_error`。修正原因且確認重複效果可接受後，才人工重送。
- `running` 且原 worker 已確定停止：先確認是否已產生效果，再決定重送；不能盲目重送。
- `running` 但不確定原 worker 是否仍在執行，或效果狀態不明：應先進一步調查。
- 若是 payload 或資料本身錯誤，直接重送仍會使用相同 payload，通常只會重現相同失敗。

以上只讀取並測試了這段流程，沒有修改程式或啟動外部服務。

## job-recovery-three-more-r1-off (openai / gpt-5.6-luna / max / off)

### Message 1

我會只追蹤任務生命週期與失敗處理：先讀 `README.md`、指定程式與 `RUNBOOK.md`，再檢視相關測試並依 README 執行本機測試；全程不修改檔案、不啟動外部服務。最後我會分開整理「程式實作」「測試已確認」「仍未知」及等待、重送、調查的判斷條件。

### Message 2

目前已讀到核心流程：`claim_ready()` 以交易把 `queued` 任務改成 `running` 並遞增嘗試次數；成功先寫 `effects` 再標記 `done`；可重試錯誤才會依延遲重新排隊。接下來我會跑 README 指定測試，並補查邊界條件（重啟、人工重送與效果重複）是否只是測試情境，還是程式有更完整的保護。

### Message 3

結論先說：這是「有限次、由例外型別決定」的重試機制；不是所有失敗都會自動恢復。重啟後只有仍在 `queued` 的任務會繼續被領取，`running` 任務不會自動回收。人工重送可能造成重複執行，現有機制沒有冪等或去重保護。

### 完整流程

| 階段 | 程式行為 |
|---|---|
| 接收 | `submit()` 將 payload、`max_attempts`、`retry_delay` 固定寫入 SQLite，狀態為 `queued`、`attempt=0`。[store.py:61](<evals/fixtures/job-recovery/store.py:61) |
| 開始執行 | `run_once()` 呼叫 `claim_ready()`；只有 `state='queued'` 且 `available_at <= now` 的任務可被領取，領取時原子地改成 `running` 並將 `attempt` 加一。[worker.py:32](<evals/fixtures/job-recovery/worker.py:32) |
| 成功 | `operation(job)` 回傳後，先寫入 `effects`，再把任務標成 `done`。[worker.py:55](<evals/fixtures/job-recovery/worker.py:55) |
| 可重試失敗 | 只有拋出 `RetryableJobError` 且尚未達上限時，才回到 `queued`，並設定 `available_at = 現在 + retry_delay`。[worker.py:39](<evals/fixtures/job-recovery/worker.py:39) |
| 達到上限 | 可重試錯誤發生在 `attempt >= max_attempts` 時，直接變成 `failed`。[worker.py:41](<evals/fixtures/job-recovery/worker.py:41) |
| 不可重試失敗 | `PermanentJobError` 與其他一般 `Exception` 都直接變成 `failed`，不會自動重試。[worker.py:46](<evals/fixtures/job-recovery/worker.py:46) |

第一次執行的嘗試次數是 1。以 `max_attempts=3` 為例，最多執行三次；人工 `resubmit()` 會把 `attempt` 重設為 0，因此這個上限是每次重送週期的上限，不是任務生命週期總上限。[store.py:133](<evals/fixtures/job-recovery/store.py:133)

### 重試到底由誰觸發

程式只負責「排程下一次可執行時間」；`queue_retry()` 不會建立計時器或背景執行緒。[store.py:116](<evals/fixtures/job-recovery/store.py:116)

下一次嘗試必須由外部反覆呼叫 `JobWorker.run_once()`，且時間已到才會被 `claim_ready()` 領取。這個 repository 沒有 worker loop、polling 或 sleep 的實作。因此 RUNBOOK 所說的「自動重試」只有在外部確實持續呼叫 worker 時才成立。

### 程式重新啟動後

SQLite 中的已提交狀態會保留：

- `queued` 且已到 `available_at`：可繼續執行。
- `queued` 但尚未到時間：繼續等待。
- `done`：不會再被領取。
- `failed`：不會自動重試。
- `running`：會一直停在 `running`，因為 `claim_ready()` 只查 `queued`，沒有 lease、timeout 或 stale-job reclaim。

測試明確確認重新開啟資料庫後，`running` 任務不會被自動領回；必須人工 `resubmit()`。[test_job_flow.py:114](<evals/fixtures/job-recovery/test_job_flow.py:114)

所以 RUNBOOK 的「重啟後會繼續處理尚未完成的任務」不能照字面採信；它只對尚未開始、或已排回 `queued` 的任務成立。

### 人工重送與重複執行

會重複，而且現有機制沒有防止：

- `resubmit()` 可作用於 `failed` 或 `running`。
- 它重用相同 payload、清除錯誤、將 `attempt` 歸零。
- `effects` 是 append-only，沒有 `(job_id, attempt)` 唯一限制或去重邏輯。[store.py:151](<evals/fixtures/job-recovery/store.py:151)
- 成功效果與 `done` 狀態是兩次分開的資料庫提交；若效果已寫入、程式在標記 `done` 前中斷，重送會再次產生效果。[worker.py:55](<evals/fixtures/job-recovery/worker.py:55)

測試已實際確認：效果已寫入後模擬崩潰，人工重送會留下兩筆效果。[test_job_flow.py:101](<evals/fixtures/job-recovery/test_job_flow.py:101)

正常領取本身有 SQLite 交易與狀態條件，可避免兩個 worker 同時正常領取同一個 `queued` 任務；但這不等於有冪等保護。若人工重送 `running` 任務時，原 worker 其實仍在執行，還可能發生並行執行與狀態互相覆寫。這部分沒有 worker ownership 或 attempt fencing，測試也未覆蓋。

另外，README 已明確說 `effects` 只是本機 stand-in，不是真實外部服務。[README.md:3](<evals/fixtures/job-recovery/README.md:3) 因此測試只能證明本機效果紀錄會重複，不能證明真實外部操作的實際結果。

### 失敗時的處置判斷

- `queued`，且 `available_at` 尚未到：等待下一次 worker 執行；不要人工重送。
- `queued`，但已到 `available_at` 卻長時間沒動：調查 worker 是否仍在 polling，因為程式本身沒有自動 loop。
- `failed` 且錯誤是暫時性原因、或只是達到重試上限：先確認外部效果是否已產生，再考慮人工重送。
- `failed` 且是 payload 無效、程式錯誤或未知例外：先調查並修正原因；直接重送只會重複相同失敗。
- `running` 且原 worker 已確認停止：先查效果紀錄與外部結果，再決定是否重送；重送可能重複執行。
- 不要只依 `last_error` 字串判斷是否可重試；資料庫沒有保存錯誤分類，需查看 worker/operation 的例外來源。`RetryableJobError` 是由 `operation` 負責正確拋出的。

### 測試與未知範圍

依 README 執行 `python3 -B -m unittest -v`，8 個測試全部通過。[README.md:5](<evals/fixtures/job-recovery/README.md:5)

測試實際確認了成功、可重試錯誤、重試上限、永久錯誤、模擬崩潰後重複效果、資料庫重開、failed/running 重送。尚未確認的包括：

- 真正的常駐 worker/polling 行為；
- 多程序並行與人工重送競態；
- 真實外部效果是否已完成；
- operation 已產生外部效果但之後拋錯的情況；
- 資料庫寫入或 `mark_done()` 失敗時的恢復；
- `config.py` 驗證邊界的測試。

因此，最安全的操作原則是：`queued` 才等待自動重試；`failed` 或重啟後的 `running` 都視為需要人工判斷，且任何重送前都要先確認是否可能已有外部效果。

## job-recovery-three-more-r1-duck (openai / gpt-5.6-luna / max / duck)

### Message 1

我會沿著任務生命週期閱讀 `store.py`、`worker.py`、`config.py`、相關測試與 `RUNBOOK.md`，再依 `README.md` 跑本機測試；只做讀取與驗證，不修改程式或啟動外部服務。最後我會把「程式實際行為、測試覆蓋、未知事項」分開，整理成故障時可用的等待／重送／調查判斷。

### Message 2

程式流程已初步對上：`worker.py` 只在捕獲 `RetryableJobError` 且尚未達上限時把任務排回佇列；永久錯誤與未預期例外直接終止。另有一個關鍵風險已出現：效果先寫入、完成狀態後寫入，兩次寫入之間若程序中斷，任務會留在 `running`，而再次人工重送會再執行一次效果。接著我會用測試與行號逐項核實，並檢查重啟與文件描述是否一致。

### Message 3

結論先說：

- 可以等待的，是 `queued` 且尚未到 `available_at` 的可重試任務；但必須有外層程式再次呼叫 `run_once()`。
- `failed` 不會自動再試；`running` 在 worker 重啟後也不會自動被收回。
- 人工 `resubmit()` 可能造成重複執行，現有程式沒有冪等、防重或舊 worker 隔離機制。
- `RUNBOOK.md` 對「所有失敗都會自動重試」及「所有未完成任務都會在重啟後繼續」的說法過於廣泛，不能直接照字面採信。

## 任務生命週期

```text
submit()
  → queued, attempt=0
  → claim_ready()（到期且可取的任務）
  → running, attempt 加一
  → operation(job)
       ├─ 成功
       │    → record_effect()
       │    → mark_done()
       │    → done
       ├─ RetryableJobError 且未達上限
       │    → queue_retry()
       │    → queued，等待 retry_delay
       ├─ RetryableJobError 且已達上限
       │    → failed
       └─ PermanentJobError 或其他例外
            → failed
```

- `submit()` 把 payload、`max_attempts`、`retry_delay` 固定寫入資料庫；預設值是最多 3 次、延遲 10 秒。[`config.py`](evals/fixtures/job-recovery/config.py:5) [`store.py`](evals/fixtures/job-recovery/store.py:61)
- `claim_ready()` 只會領取 `state='queued'` 且 `available_at <= now` 的任務，領取時將狀態改成 `running`，並把 `attempt` 加一。[`store.py`](evals/fixtures/job-recovery/store.py:81)
- 成功時，效果紀錄先提交，任務完成狀態後提交，兩者不是同一個交易。[`worker.py`](evals/fixtures/job-recovery/worker.py:32)
- `RetryableJobError` 才會自動排隊重試；`PermanentJobError` 和其他未預期例外都直接變成 `failed`。[`worker.py`](evals/fixtures/job-recovery/worker.py:37)
- `max_attempts` 是總執行次數，不是重試次數。例如上限為 3 時，第三次遇到可重試錯誤就失敗，不會有第四次。

程式中只有一次性的 `run_once()`，沒有看到輪詢、睡眠或背景排程迴圈。因此「自動重試」實際上是：worker 外層持續呼叫 `run_once()`，且下一次呼叫時間已達 `available_at`。時間到本身不會觸發執行。

## 重啟後的行為

SQLite 會保留任務狀態，但重新建立 `JobStore` 不會修復狀態：

| 重啟時狀態 | 重啟後行為 |
|---|---|
| `queued` 且已到 `available_at` | 可被下一次 `claim_ready()` 領取 |
| `queued` 但尚未到時間 | 繼續等待 |
| `running` | 保持 `running`，不會被自動收回 |
| `failed` | 保持 `failed`，不會自動重試 |
| `done` | 保持完成 |

`claim_ready()` 明確只查詢 `queued`，沒有 lease、逾時、heartbeat 或啟動時復原 `running` 的邏輯。[`store.py`](evals/fixtures/job-recovery/store.py:85)

測試實際確認了：重啟後 `running` 任務不會被重新領取，必須人工 `resubmit()` 才能繼續。[`test_job_flow.py`](evals/fixtures/job-recovery/test_job_flow.py:114)

因此 RUNBOOK 的「worker 重啟後會繼續處理尚未完成的任務」只有對尚未被領取、仍為 `queued` 的任務成立；對 `running` 或 `failed` 任務不成立。[`RUNBOOK.md`](evals/fixtures/job-recovery/RUNBOOK.md:5)

## 人工重送與重複執行

`resubmit()` 允許重送 `running` 或 `failed` 任務，會：

- 保留同一個 job ID 和 payload；
- 將 `attempt` 重設為 0；
- 立即改回 `queued`；
- 清除 `last_error`；
- 保留舊的 `effects` 紀錄。[`store.py`](evals/fixtures/job-recovery/store.py:133)

這不是防重機制。`effects` 表沒有 `job_id + attempt` 的唯一限制，也沒有檢查先前是否已產生效果。

測試直接確認了這個風險：程序在寫入效果後、寫入 `done` 前崩潰，任務留在 `running`；人工重送後再次執行，效果紀錄變成兩筆。[`test_job_flow.py`](evals/fixtures/job-recovery/test_job_flow.py:101)

此外，重送 `running` 任務時，原本的 worker 並沒有被取消或隔離。若原 worker 仍在執行，新的 worker 可能同時執行同一 payload；完成狀態更新也只檢查 job ID 和 `running` 狀態，沒有檢查 attempt 世代。這是程式碼可推得的競態風險，測試沒有涵蓋真正的並行情境。

README 已說明 `effects` 只是本機 stand-in，不是真實外部服務。因此測試能證明本機效果紀錄會重複，不能證明真實外部操作一定重複或一定安全。[`README.md`](evals/fixtures/job-recovery/README.md:1)

## 測試確認與未知範圍

依 README 執行：

```sh
python3 -B -m unittest -v
```

結果是 8 個測試全部通過。測試確認了：

- 成功流程、attempt 計數與效果紀錄；
- 可重試錯誤的延遲與上限；
- 上限前恢復成功；
- 永久錯誤不重試；
- 效果已寫入但完成狀態尚未寫入時的重複效果；
- 重啟不會收回 `running`；
- `failed`／`running` 重送會重設 attempt 並沿用 payload。

目前未被測試確認的部分包括：

- 真正的 worker 輪詢／排程器是否存在於這個範圍之外；
- 多程序並行下的重送競態；
- 真實外部副作用；
- 資料庫寫入失敗、`record_effect()` 或 `mark_done()` 失敗時的行為；
- 僅從資料庫恢復時如何判斷原本是可重試錯誤還是永久錯誤。

特別是，資料庫只保存 `last_error` 字串，沒有保存錯誤分類；任務事後變成 `failed` 時，不能單靠資料庫欄位確定它原本是否為 `RetryableJobError`。

## 故障時的判斷

- `queued` 且 `available_at` 尚未到：等待；確認有外層 worker 會再次呼叫 `run_once()`。
- `queued` 且已到時間但沒有進展：不要無限等待，先調查 worker 是否仍在運作；此狀態不能用 `resubmit()`。
- `failed` 且已確認原因是暫時性問題、也確認沒有已產生的外部效果：修復原因後可重送。
- `failed` 且是 payload 錯誤、未預期例外、或原因不明：先調查；直接重送同一 payload 通常只會重複失敗。
- `running` 出現在重啟後或崩潰後：先確認舊 worker 已停止，再查效果紀錄及真實外部系統；未確認前不要盲目重送。
- 已達 `max_attempts`：自動重試已停止。人工重送會把計數歸零，重新取得完整嘗試額度，因此應把它視為一次新的風險決策，而不是單純「繼續原重試」。

## job-recovery-three-more-r2-off (openai / gpt-5.6-luna / max / off)

### Message 1

我會只沿著「接收 → 執行 → 成功/失敗 → 重試/重啟恢復」這條流程，逐一核對 `store.py`、`worker.py`、`config.py`、相關測試與 `RUNBOOK.md`，並依 README 跑本機測試；不會修改檔案或啟動外部服務。

### Message 2

目前已讀到核心實作：重試判斷在 `worker.py`，延遲排程與狀態轉換在 `store.py`；另外已看到一個關鍵風險：效果紀錄先寫入、任務完成後寫入，兩者之間若程序中斷，任務會停在 `running`。接著我會跑 README 指定測試，並把每個狀態轉換與文件說法對上。

### Message 3

結論：這套程式是「有限次重試 + 人工恢復」，不是自動接管所有未完成任務，也沒有 exactly-once 或冪等保護。

## 完整流程

```text
submit
  → queued, attempt=0
  → claim_ready
  → running, attempt += 1
      ├─ 成功：record_effect → mark_done
      ├─ RetryableJobError 且未達上限：queued，等待 retry_delay
      ├─ RetryableJobError 且已達上限：failed
      ├─ PermanentJobError：failed
      └─ 其他 Exception：failed
```

- `submit()` 將 payload、`max_attempts`、`retry_delay` 固定寫入 SQLite；沒有獨立的 `accepted` 狀態，提交後就是 `queued`。[store.py:61](evals/fixtures/job-recovery/store.py:61) [config.py:6](evals/fixtures/job-recovery/config.py:6)
- `claim_ready()` 只會領取 `state='queued'` 且 `available_at <= now` 的任務，並將 `attempt` 增加後改為 `running`。[store.py:81](evals/fixtures/job-recovery/store.py:81)
- 真正的重試判斷由 `JobWorker.run_once()` 觸發：只有 operation 主動拋出 `RetryableJobError` 才會呼叫 `queue_retry()`。[worker.py:32](evals/fixtures/job-recovery/worker.py:32)
- `queue_retry()` 將任務排回 `queued`，下一次可執行時間是 `now + retry_delay`。[store.py:116](evals/fixtures/job-recovery/store.py:116)
- `max_attempts` 是總執行次數，不是重試次數。預設是 3；第 3 次仍是 retryable failure 時就進入 `failed`。[config.py:8](evals/fixtures/job-recovery/config.py:8) [worker.py:39](evals/fixtures/job-recovery/worker.py:39)
- `PermanentJobError` 與其他例外都不重試，直接 `failed`。[worker.py:46](evals/fixtures/job-recovery/worker.py:46)
- 成功時先寫入 `effects`，再把任務標成 `done`；兩者是分開的持久化操作。[worker.py:55](evals/fixtures/job-recovery/worker.py:55)

因此，「自動重試」實際上是：

1. operation 拋出正確的 `RetryableJobError`。
2. worker 呼叫 `queue_retry()`。
3. 後續再次呼叫 `run_once()`，且時間已到 `available_at`。

這些檔案中沒有常駐迴圈、排程器或 timer；`run_once()` 本身只處理一個任務。

## 程式重啟後的行為

SQLite 會保留狀態，但啟動時沒有把 `running` 任務重新排回 `queued` 的 recovery 邏輯。`claim_ready()` 只查 `queued`。[store.py:87](evals/fixtures/job-recovery/store.py:87)

所以：

- `queued` 且已到時間：重啟後仍可被領取。
- `queued` 但尚未到 `available_at`：繼續等待。
- `running`：會永久留在 `running`，不會被新 worker 自動接管。
- `failed`：維持失敗，不會自動重試。
- `done`：維持完成。

測試明確確認了重新開啟資料庫後，`running` 任務不會被重新領取。[test_job_flow.py:114](evals/fixtures/job-recovery/test_job_flow.py:114)

## 人工重送是否會重複執行

會，而且現有機制沒有真正處理這個問題。

`resubmit()`：

- 可對 `failed` 或 `running` 任務使用。
- 使用相同的 `job_id` 與 payload。
- 將 `attempt` 重設為 0。
- 不會刪除既有 `effects`，也沒有冪等鍵或效果去重。[store.py:133](evals/fixtures/job-recovery/store.py:133)

測試直接模擬了「效果已寫入、完成狀態尚未寫入」的 crash：任務留在 `running`，人工重送後再次產生效果，`effects` 從 1 筆變成 2 筆。[test_job_flow.py:101](evals/fixtures/job-recovery/test_job_flow.py:101)

另外，`resubmit()` 允許重送 `running` 任務。如果舊 worker 其實仍在執行，人工重送可能造成兩個執行重疊。程式也沒有 worker ownership、lease、generation token 或 heartbeat 來阻止舊 worker 寫入新一輪狀態。

`effects` 是 append-only 紀錄，不能當成去重機制。README 也明確說它只是本機 stand-in，不是真實外部服務。[README.md:3](evals/fixtures/job-recovery/README.md:3)

## 文件與實作不一致

`RUNBOOK.md` 有兩個說法不能直接採信：

- 「若執行失敗，失敗會自動重試」過度概括：只有 `RetryableJobError` 會重試；永久錯誤與一般例外會立即失敗，而且還需要後續 worker 呼叫 `run_once()`。[RUNBOOK.md:5](evals/fixtures/job-recovery/RUNBOOK.md:5)
- 「worker 重啟後會繼續處理尚未完成的任務」對 `running` 任務是錯的；重啟只會讓仍為 `queued` 的任務有機會被處理。[RUNBOOK.md:6](evals/fixtures/job-recovery/RUNBOOK.md:6)

「可以人工重送」這件事本身有程式支援，但 RUNBOOK 沒有提醒重複效果風險，也沒有說明必須先確認舊 worker 已停止。[RUNBOOK.md:7](evals/fixtures/job-recovery/RUNBOOK.md:7)

## 測試確認範圍

依 README 執行：

```text
Ran 8 tests
OK
```

測試確認了：

- 成功任務會完成並記錄效果。
- retryable failure 會依固定延遲重試，並在上限失敗。
- retryable failure 可在上限前恢復。
- permanent failure 不會重試。
- crash window 會留下 `running`，並可能重複效果。
- 重啟後不會自動 reclaim `running` 任務。
- `failed` 與 `running` 任務可重送，payload 重用、attempt 重設。

測試沒有確認：

- 真正的常駐 worker 迴圈或排程器如何反覆呼叫 `run_once()`。
- 多個 worker 與人工重送同時發生時的競態。
- 真實外部服務是否提供冪等或去重。
- operation 在拋出例外前已產生外部效果的情況。
- SQLite、程序被硬殺，以及其他未明確模擬的 crash window。

## 實務判斷

- `queued` 且 `now < available_at`：等待；這通常是排程中的自動重試。
- `queued` 且已超過 `available_at`：不必人工重送；先確認 worker 是否仍在持續呼叫 `run_once()`。長時間未被領取就應調查。
- `failed`：不會再自動執行。先查看 `last_error`、`attempt` 與效果紀錄；修正原因且確認可安全重做後再重送。
- `running`：先確認舊 worker 是否仍活著，以及是否可能已產生效果。只有確認舊執行已停止後才考慮重送，而且仍需接受重複執行風險。
- `done`：不需重送。

最重要的限制是：資料庫只保存錯誤文字，不保存錯誤分類；因此不能單靠 `last_error` 穩健判斷它原本是 retryable、permanent 還是一般例外。[store.py:175](evals/fixtures/job-recovery/store.py:175)

## job-recovery-three-more-r2-duck (openai / gpt-5.6-luna / max / duck)

### Message 1

我會只沿著任務生命週期追查：先讀 `store.py`、`worker.py`、`config.py`、測試、`RUNBOOK.md` 與 `README.md`，再執行 README 指定的本機測試；最後把「程式實際行為」「測試驗證範圍」「仍無法確定的部分」分開整理，不修改檔案也不啟動外部服務。

### Message 2

目前程式已呈現一個重要差異：工作程序會自動把可重試錯誤重新排回佇列，但重啟後不會自動接管仍是 `running` 的任務；`RUNBOOK.md` 對重啟後會繼續處理的描述因此需要核對。接著我會用 README 指定命令跑測試，並檢查各狀態轉移與人工重送的邊界。

### Message 3

測試全部通過（8/8）。測試也直接確認兩個關鍵結果：重試上限到達後會進入 `failed`，而效應已寫入但完成標記尚未寫入時，人工重送會留下兩筆效應紀錄。現在只差把程式沒有涵蓋的自動化與併發邊界，和文件的過度描述分開列清楚。

### Message 4

結論：只有「明確被分類為可重試、且尚未達到最大嘗試次數」的失敗可以等待；永久錯誤、非預期例外、重試次數用盡，以及重啟後卡在 `running` 的任務，都不能直接假設會自動恢復。人工重送確實可能造成重複執行，現有程式沒有冪等或去重機制。

## 完整流程

```text
submit
  ↓
queued，attempt=0
  ↓ available_at 到期且 worker 呼叫 run_once
claim_ready
  ↓
running，attempt 加 1
  ├─ 成功 → 寫入 effects → done
  ├─ RetryableJobError 且尚未達上限 → queued，等待 retry_delay
  ├─ RetryableJobError 且已達上限 → failed
  ├─ PermanentJobError → failed
  └─ 其他例外 → failed
```

- `submit()` 將任務、payload、`max_attempts`、`retry_delay` 一起寫入 SQLite；這些設定是提交時固定保存的。[store.py:61](evals/fixtures/job-recovery/store.py:61)、[config.py:5](evals/fixtures/job-recovery/config.py:5)
- `claim_ready()` 只領取 `state='queued'` 且 `available_at <= now` 的任務，領取時才將 `attempt` 加一並改成 `running`。[store.py:81](evals/fixtures/job-recovery/store.py:81)
- 成功時先寫入 `effects`，再把任務標成 `done`。[worker.py:55](evals/fixtures/job-recovery/worker.py:55)
- `RetryableJobError` 在尚未達上限時由 worker 呼叫 `queue_retry()`，設定下一次可執行時間為 `now + retry_delay`。[worker.py:39](evals/fixtures/job-recovery/worker.py:39)
- 嘗試次數達到 `max_attempts` 後，當次可重試錯誤會直接進入 `failed`；`PermanentJobError` 和其他例外則第一次發生就進入 `failed`。[worker.py:41](evals/fixtures/job-recovery/worker.py:41)

## 重試由誰觸發

程式中沒有獨立的排程器、sleep loop 或背景 polling loop。

實際行為是：

1. `JobWorker.run_once()` 捕捉 `RetryableJobError`。
2. 它把任務重新設為 `queued`，並寫入 `available_at`。
3. 之後必須再次有人呼叫 `run_once()`，而且時間已到，任務才會被領取。

因此 `RUNBOOK.md` 所說的「自動重試」只能有限度採信：程式會自動重新排隊，但沒有在這些檔案中實作「等待後自動再次執行」的 worker loop。[RUNBOOK.md:5](evals/fixtures/job-recovery/RUNBOOK.md:5)

## 程式重新啟動後

SQLite 中的狀態會保留，但新 worker 只會領取 `queued` 任務：

| 重啟時狀態 | 重啟後行為 |
|---|---|
| `queued` 且已到 `available_at` | 可被新 worker 領取 |
| `queued` 但尚未到時間 | 繼續等待 |
| `running` | 不會被重新領取，會一直停留在 `running` |
| `failed` | 不會自動重試，需人工 `resubmit()` |
| `done` | 不再執行 |

所以 `RUNBOOK.md` 的「worker 重啟後會繼續處理尚未完成的任務」不應直接採信；它對 `queued` 任務大致成立，但對已經是 `running` 的未完成任務是錯的。[RUNBOOK.md:6](evals/fixtures/job-recovery/RUNBOOK.md:6)

測試 `test_restart_does_not_reclaim_running_job` 直接確認：重新開啟 `JobStore` 後，`running` 任務不會被自動領取，只能先人工重送。[test_job_flow.py:114](evals/fixtures/job-recovery/test_job_flow.py:114)

## 人工重送與重複執行

`resubmit()` 允許重送 `running` 或 `failed` 任務，會：

- 使用相同的 job ID 和 payload；
- 將 `attempt` 重設為 `0`；
- 清除 `last_error`；
- 立即放回 `queued`；
- 等於重新取得完整的重試額度。[store.py:133](evals/fixtures/job-recovery/store.py:133)

這沒有檢查既有 `effects`，也沒有冪等鍵或唯一限制。`effects` 表甚至允許同一任務留下多筆紀錄。[store.py:151](evals/fixtures/job-recovery/store.py:151)

測試已確認具體重複情境：

1. 效果已寫入；
2. 程式在寫入 `done` 前崩潰；
3. 任務仍是 `running`；
4. 人工重送；
5. 再執行一次後產生兩筆效果紀錄。[test_job_flow.py:101](evals/fixtures/job-recovery/test_job_flow.py:101)

因此不能把 `done` 以外的狀態視為「尚未產生外部效果」。README 也明確說 `effects` 只是本機 stand-in，不是真實外部服務，所以實際外部服務是否已成功、是否會重複，這份程式無法判定。[README.md:3](evals/fixtures/job-recovery/README.md:3)

## 故障處理判斷

- `queued`、尚未到 `available_at`，且原因是可重試錯誤：等待；但要確認確實有程序會再次呼叫 `run_once()`。
- `queued` 且已到時間：讓 worker 正常領取，不需要人工重送。
- `failed` 且是永久錯誤、非預期例外或已達重試上限：先調查並修正原因，再人工重送。
- 重啟後長時間維持 `running`：先確認原 worker 已停止，並檢查本機效果紀錄及實際外部結果；不能直接盲目重送。
- 已有 `effects` 但任務不是 `done`：視為可能重複執行，人工重送前必須先調查。
- `done`：不應再重送。

## 測試確認與未知範圍

README 指定的 `python3 -B -m unittest -v` 已執行成功，8 個測試全部通過。測試確認了成功、可重試失敗、達上限、永久失敗、重啟不回收 `running`，以及重送造成重複效果等情境。

目前仍未確認的部分包括：

- 是否有外部程式負責持續呼叫 `run_once()`；
- 真實外部服務在「已完成但本地未標記完成」時的結果；
- 原 worker 尚未停止時，另一個 worker 同時重送的行為；
- stale `running` 任務是否有外部清理機制；
- 真實錯誤是否會正確拋出 `RetryableJobError`。資料庫只保存錯誤文字，沒有保存錯誤分類。

因此，最安全的原則是：可重試且仍有額度的 `queued` 任務才等待；任何 `running`、`failed` 或已有效果紀錄的任務，都先調查再決定是否重送。

## job-recovery-three-more-r3-off (openai / gpt-5.6-luna / max / off)

### Message 1

我會只追這條任務生命週期：接收、領取、執行、成功/失敗、重試、重啟恢復與人工重送；先讀 `store.py`、`worker.py`、`config.py`、測試、`RUNBOOK.md`/`README.md`，再依 README 跑本機測試，最後分開整理「程式實作」「測試已證實」「仍未知」與操作判斷條件。全程不修改程式、不啟動外部服務。

### Message 2

檔案很小但有一個關鍵語意差異已浮現：`RUNBOOK.md` 把「重啟後會繼續處理尚未完成任務」寫得很概括，而目前 `claim_ready()` 只挑 `queued` 任務，`running` 任務不會被自動接回。我先跑完整測試並再檢查狀態轉移與邊界條件，確認這不是測試解讀偏差。

### Message 3

本機測試共 8 項，全部通過。測試已直接證實兩個重點：重試只在 `RetryableJobError` 且尚未達上限時排回佇列；重新啟動不會自動回收 `running` 任務。另有測試明確看到重送後 `effects` 會有兩筆，因此不能把同一 `job_id` 視為「只執行一次」。

### Message 4

結論：只有「仍是 `queued`、且尚未超過重試上限」的任務可以等待自動恢復。`failed` 是終態；程式重啟後，`running` 任務不會自動被重新領取。人工重送可能造成重複執行，現有機制沒有提供冪等或去重保護。

### 完整流程

| 階段 | 程式行為 |
|---|---|
| 提交 | 建立 `queued` 任務，`attempt=0`，並把 `max_attempts`、`retry_delay` 固定寫入該任務。預設為最多 3 次、間隔 10 秒。[config.py](evals/fixtures/job-recovery/config.py:5) [store.py](evals/fixtures/job-recovery/store.py:61) |
| 領取 | `claim_ready()` 只找 `state='queued'` 且 `available_at <= now` 的任務，原子地改成 `running`，並把 `attempt` 加一。[store.py](evals/fixtures/job-recovery/store.py:81) |
| 執行成功 | 先寫入 `effects`，再把任務改成 `done`。這是兩次獨立提交，不是單一交易。[worker.py](evals/fixtures/job-recovery/worker.py:55) |
| 可重試錯誤 | 只有執行函式明確拋出 `RetryableJobError` 才會重試。若尚未達上限，改回 `queued`，並將 `available_at` 設為現在加上延遲。[worker.py](evals/fixtures/job-recovery/worker.py:39) |
| 達到上限 | 當前一次已是第 `max_attempts` 次時，直接改成 `failed`，不再排隊。[worker.py](evals/fixtures/job-recovery/worker.py:41) |
| 永久或非預期錯誤 | `PermanentJobError` 和其他一般 `Exception` 都直接變成 `failed`，不會自動重試。[worker.py](evals/fixtures/job-recovery/worker.py:46) |

重試是 `JobWorker.run_once()` 在捕捉到 `RetryableJobError` 後呼叫 `queue_retry()` 觸發的；`queue_retry()` 只寫入資料庫，不負責等待或啟動下一次執行。必須有後續的 worker 呼叫 `run_once()`，任務才會在到期後再次被領取。

### 重啟後的行為

- `queued` 任務會保留在 SQLite；到 `available_at` 後可被重新領取。
- 延遲中的 `queued` 任務會繼續等待。
- `running` 任務不會被重新領取，因為 `claim_ready()` 完全不查 `running`。
- `done`、`failed` 不會自動再執行。

測試直接確認了「重開資料庫後，`running` 任務仍不會被回收」。[test_job_flow.py](evals/fixtures/job-recovery/test_job_flow.py:114)

因此，`RUNBOOK.md` 的「worker 重啟後會繼續處理尚未完成的任務」不能照字面採信；它只對尚未開始或已排回佇列的任務成立，對 `running` 任務不成立。[RUNBOOK.md](evals/fixtures/job-recovery/RUNBOOK.md:5)

### 人工重送與重複執行

`resubmit()` 允許重送 `running` 或 `failed` 任務，會：

- 保留同一個 `job_id` 和 payload；
- 將狀態改回 `queued`；
- 把 `attempt` 重設為 0；
- 清除 `last_error`；
- 不清除既有 `effects`。[store.py](evals/fixtures/job-recovery/store.py:133)

這會造成重複執行。測試模擬「效果已寫入、但完成狀態尚未寫入」的崩潰，之後重送同一任務，結果得到兩筆效果紀錄。[test_job_flow.py](evals/fixtures/job-recovery/test_job_flow.py:101)

現有機制沒有：

- effect 的唯一性限制；
- idempotency key；
- worker lease 或 fencing token；
- 以 `attempt` 驗證回報者仍是目前執行者。

所以若舊 worker 其實尚未停止，管理員把 `running` 任務重送後，舊 worker 甚至可能寫入效果或把新執行的狀態改成完成。這是程式碼可推導出的風險，測試沒有涵蓋併發情境。

README 的限制說明是可信的：`effects` 只是本機 stand-in，不是真實外部服務，因此無法由這些測試證明實際寄送、付款或其他外部操作是否真的重複。[README.md](evals/fixtures/job-recovery/README.md:3)

### 實務判斷

- `queued` 且 `available_at` 尚未到：等待；這是正常重試延遲。
- `queued` 且已到 `available_at`：應由 worker 處理；若長時間不動，調查 worker 是否仍在輪詢。單純等待不會自行觸發程式。
- `failed` 且錯誤是永久錯誤或一般非預期錯誤：先調查並修正原因，再考慮重送。
- `failed` 且是可重試錯誤但已達上限：不會再自動恢復；修正原因後才人工重送。
- `running` 且 worker 仍可能活著：先等待或確認舊 worker 狀態，不要立即重送。
- `running` 且確認 worker 已中止：先確認操作是否可能已產生外部效果，再決定是否接受重複風險後重送。
- 已有 `effects`，或外部效果狀態不明：應先調查，不應盲目重送。

本次依 README 執行 `python3 -B -m unittest -v`，8 項測試全部通過。測試確認了成功、可重試錯誤、達上限、永久錯誤、模擬崩潰、重啟不回收，以及人工重送重設次數；但沒有確認實際外部服務、真正多程序併發、worker 輪詢迴圈，或操作本身的冪等性。

## job-recovery-three-more-r3-duck (openai / gpt-5.6-luna / max / duck)

### Message 1

我會沿著任務生命週期比對 `store.py`、`worker.py`、`config.py`、測試與 `RUNBOOK.md`，再依 `README.md` 跑本機測試；重點是確認重試觸發者、停止條件、重啟後的未完成任務，以及人工重送的重複執行風險。整個過程只讀取與測試，不修改程式或啟動外部服務。

### Message 2

程式與測試已顯示一個關鍵分界：可重試錯誤會由 worker 重新排隊，但資料庫中的 `running` 任務沒有逾時接管或重啟自動回收；我接著會用本機測試確認這些路徑，並核對操作筆記哪些敘述因此過度概括。

### Message 3

本機測試 8/8 通過，已實際確認成功、延遲重試、達上限後失敗、永久錯誤、重啟不接管 `running`，以及重送可能留下兩筆效果紀錄。接下來我會整理成操作判斷表，並把「程式可直接讀出的行為」與「測試覆蓋／仍需外部資訊」分開。

### Message 4

結論：這套系統不是「恰好執行一次」。可重試錯誤會自動重新排隊，但 `running` 任務在重啟後不會自動接管；人工重送確實可能造成重複執行，而且現有程式沒有冪等或去重機制。

### 完整流程

```text
submit
  → queued, attempt=0
  → worker.claim_ready()
  → running, attempt+1
      ├─ 成功 → 寫入 effects → done
      ├─ RetryableJobError 且尚未達上限 → queued，等待 retry_delay
      ├─ RetryableJobError 且已達上限 → failed
      └─ PermanentJobError／其他 Exception → failed
```

- 提交時會把 `max_attempts` 與 `retry_delay` 固定寫入該任務；預設是 3 次、延遲 10 秒。[config.py](evals/fixtures/job-recovery/config.py:5)、[store.py](evals/fixtures/job-recovery/store.py:61)
- `claim_ready()` 只會領取 `state='queued'` 且 `available_at <= now` 的任務，領取時才把 `attempt` 加一。[store.py](evals/fixtures/job-recovery/store.py:81)
- 重試是 `JobWorker.run_once()` 捕捉 `RetryableJobError` 後呼叫 `queue_retry()` 觸發的；程式本身沒有看到常駐 polling loop 或排程器，因此必須有人持續呼叫 worker。[worker.py](evals/fixtures/job-recovery/worker.py:32)
- `max_attempts` 是總執行次數，不是額外重試次數。達上限後，下一次可重試錯誤會直接變成 `failed`。
- `PermanentJobError` 與其他一般例外不會自動重試，會立即進入 `failed`。[worker.py](evals/fixtures/job-recovery/worker.py:39)

成功時，效果紀錄與任務完成是兩次不同的資料庫提交：先寫 `effects`，再把任務改成 `done`。[worker.py](evals/fixtures/job-recovery/worker.py:55)

### 程式重啟後

- `queued` 任務會留在資料庫；到 `available_at` 後，新的 worker 可以領取。
- `running` 任務會繼續保持 `running`。新的 worker 不會領取它，程式沒有 lease、逾時、heartbeat 或啟動時 recovery。
- `failed` 與 `done` 也不會自動改變狀態。

測試實際確認了重新開啟同一個 SQLite 後，`running` 任務仍不會被新 worker 領取。[test_job_flow.py](evals/fixtures/job-recovery/test_job_flow.py:114)

因此 `RUNBOOK.md` 的「worker 重啟後會繼續處理尚未完成的任務」不能直接當成一般規則；它只適用於仍是 `queued` 且已到可執行時間的任務，不能涵蓋 `running`。[RUNBOOK.md](evals/fixtures/job-recovery/RUNBOOK.md:3)

### 人工重送與重複執行

`resubmit()` 可以處理 `failed` 或 `running` 任務，會：

- 使用同一個 `job_id` 與 payload；
- 將 `attempt` 重設為 0；
- 立即重新排隊；
- 清除 `last_error`；
- 不檢查是否已產生效果。[store.py](evals/fixtures/job-recovery/store.py:133)

因此人工重送可能重新執行整個任務，甚至重新取得一整組 `max_attempts`。`effects` 表沒有針對 `job_id` 的唯一限制，每次成功都會新增一筆。

測試已實際模擬「效果已寫入、但在標記 `done` 前崩潰」：

1. 任務停在 `running`；
2. 已有一筆效果紀錄；
3. 人工重送；
4. 再執行後變成兩筆效果紀錄。

[test_job_flow.py](evals/fixtures/job-recovery/test_job_flow.py:101)

程式也沒有 worker ownership token。因此若舊 worker 其實仍在執行，人工重送後可能與新 worker 同時處理同一任務；測試沒有覆蓋這種競態，但程式碼沒有防護。

### 失敗時的處理判斷

| 條件 | 建議 |
|---|---|
| `queued`，且 `available_at` 尚未到 | 等待；確認 worker 仍會持續呼叫 `run_once()` |
| `queued`，已到 `available_at` 但沒有進展 | 調查 worker 是否存活、是否仍在 polling；這不是應直接重送的狀態 |
| `failed`，原因是暫時性問題且已達重試上限 | 先確認原因已改善，再考慮人工重送 |
| `failed`，是 payload、目的地或其他永久錯誤 | 先修正輸入或根因，再決定是否重送 |
| `running`，worker 仍確認活著 | 等待或調查執行中的操作 |
| `running`，worker 已停止或重啟後留下 | 先確認舊 worker 已確實停止及外部效果狀態，再考慮重送 |
| 已有效果紀錄，狀態不是 `done` | 優先調查；直接重送有重複效果風險 |
| `done` | 不應重送；`resubmit()` 也不接受此狀態 |

### 測試範圍與未知部分

本機測試依 README 執行，8 個測試全部通過；已確認成功、延遲重試、重試恢復、達上限失敗、永久錯誤、重啟不接管 `running`，以及重送造成重複效果。[README.md](evals/fixtures/job-recovery/README.md:5)

仍未由測試確認的部分包括：

- 真實 worker 是否有外部常駐迴圈或 supervisor；
- 真實外部服務是否支援冪等或去重；
- 任務在 `operation()` 內已產生外部效果、但之後拋錯時的實際結果；
- 多個 worker 或人工重送同時發生時的競態；
- 其他崩潰時點的行為。

`effects` 只是本機 stand-in，不是真實外部服務紀錄，因此不能把「沒有 `effects`」解讀成「外部一定沒有發生效果」。[README.md](evals/fixtures/job-recovery/README.md:3)

