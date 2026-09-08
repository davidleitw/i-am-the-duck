# Job recovery fixture

這是一個只在本機執行的小型背景任務流程。SQLite 保存任務與效果紀錄；`effects` 是外部效果的 stand-in，不是真實服務。

執行測試：

```sh
python3 -B -m unittest -v
```

`config.py`、`store.py`、`worker.py`、`test_job_flow.py` 與 `RUNBOOK.md` 一起描述任務狀態、延遲重試、人工重送和本機效果紀錄。
