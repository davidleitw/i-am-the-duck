# Publication recovery fixture

這是一個只在本機執行的報表發布流程。catalog 與 object storage stand-in 使用兩個 SQLite
資料庫；不連接真實服務，也不模擬多執行緒。`publisher.py` 是唯一的發布、恢復與讀取入口。

從 `Publisher(catalog_path, storage_path)` 進入；`request`、`claim`、`deliver`、`scan_once`
與 `read_current` 對應要求、領取、發布、明確恢復和讀取。`Catalog` 與 `Storage` 提供本機狀態查詢。
測試會先在 stand-in 放入既有的第 6 版；服務啟動本身不會替它上傳或掃描工作。

執行測試：

```sh
python3 -B -m unittest -v
```

時間由呼叫者傳入，測試用 `SimulatedCrash` 表示兩個 durable write 之間的中斷。
