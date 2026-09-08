# Retention prune fixture

這是一個只在本機執行的小型備份快照保留清理流程。SQLite 保存快照目錄與狀態轉換紀錄；`payload_removals` 是實際刪除資料的 stand-in，不是真實儲存後端。

執行測試：

```sh
python3 -B -m unittest -v
```

`policy.py`、`catalog.py`、`pruner.py`、`test_prune.py` 與 `NOTES.md` 一起描述保留規則、清理計畫、實際刪除與中斷後的狀態。
