# 操作觀察

- 先查 object storage 的物件與 `put` 呼叫紀錄，再查 catalog 的 job receipt、status、lease token 與 deadline。
- `requested_revision` 表示目前要求的版本；`active_revision` 才是固定入口使用的版本。
- 服務啟動時只開啟兩個本機資料庫；要恢復可處理的工作，必須另外執行一次 `scan_once`。
- 這個 stand-in 只可觀察本機流程，不能推論真實 provider 的 idempotency、多程序鎖定或斷電後 durability。
