# TODO

只放還沒做的事。做完就整條刪掉，`git log` 才是歷史。每條自成一體：問題是什麼、在哪個檔、做完長什麼樣。

## repo 還是私有的

`gh repo view davidleitw/i-am-the-duck` 回 `"visibility":"PRIVATE"`，description、homepage、topics 也都是空的。README 和 `docs/README.zh-TW.md` 開頭那兩組安裝指令，別人一步都走不了。做完長這樣：repo 公開，`gh repo edit` 把說明欄位補上。

## 照 README 逐字裝一次

Claude Code 那組跑成功過，但那是因為 repo 擁有者讀得到自己的私有 repo，換成別人會失敗。Codex 那組（`codex plugin marketplace add` 加 `codex plugin add`）從沒跑過，目前是用本機資料夾當來源裝的。repo 公開後在乾淨的地方、用一個讀不到私有 repo 的身分，照兩份 README 逐字跑一次。這一趟順便驗兩件事：`.codex-plugin/plugin.json` 的 interface 現在填了 displayName、shortDescription、longDescription、developerName、category、capabilities、websiteURL、logo、composerIcon，手動放進快取讀得出來，但 `codex plugin add` 的檢查可能更嚴；`.agents/plugins/marketplace.json` 裡的 `"authentication": "ON_INSTALL"` 對公開 repo 大概不需要，沒驗過。兩個 host 都裝得起來就刪掉這條。

## 壓縮後 Codex 會不會重新提醒，還沒實測

Claude Code 壓縮後會用 `source: "compact"` 再跑一次 SessionStart，`hooks/hooks.json` 的 matcher 有列 compact，`hooks/session-start.mjs` 讀 stdin 分辨得出來，這條路驗過了。Codex 的 SessionStart 送進來的 source 也包含 compact，所以同一條路應該通，但沒實測。驗法：在 Codex 裡把對話撐到壓縮，看 agent 有沒有重新載入。真的不通再考慮 Codex 那個獨立的 PostCompact 事件，但注意 PostCompact 不會傳 source 進來，`hooks/session-start.mjs` 得改成從命令列參數判斷，而且 `hooks/hooks.json` 是兩個 host 共用的。

## 還沒有評測題目

`claude plugin eval` 會把同一道題跑兩次（載入這個外掛、不載入），照寫好的標準打分並報出差距，正好是這個外掛要證明的事。題目放在 `evals/<名字>/prompt.md`，打分標準放在 `evals/<名字>/graders/`，`claude plugin eval init --bare` 會產生範本。題目要引誘 agent 講速記才測得出差距，候選五道：計畫裡有「Phase 2」這種標籤、測試有一個失敗、沒裝 node_modules 所以不能說「通過」、一個要動三個檔的任務、把查證丟給別的 agent。前三道用字串比對打分，後兩道交給小模型判斷。這個指令目前是早期功能，預設關閉。`claude plugin eval` 只跑 Claude Code，Codex 那半沒有現成工具。

## 沒有 .gitignore

repo 根目錄沒有 `.gitignore`。目前沒有 `.DS_Store` 被追蹤（`git ls-files` 確認過），但這是 macOS，遲早會混進去。

## 版本沒有 tag

`.claude-plugin/plugin.json` 和 `.codex-plugin/plugin.json` 都是 0.0.1，git 上沒有對應的 tag。`claude plugin tag` 會建 `i-am-the-duck--v0.0.1`，並檢查兩個設定檔和 marketplace 條目對得上。公開前跑一次。
