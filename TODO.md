# TODO

只放還沒做的事。做完就整條刪掉，`git log` 才是歷史。每條自成一體：問題是什麼、在哪個檔、做完長什麼樣。

## Codex 壓縮後會不會重新提醒

Claude Code 在對話壓縮後會以 `source: "compact"` 再跑一次 SessionStart，`hooks/hooks.json` 的 matcher 有列 compact。Codex 另有獨立的 `post_compact` 事件，SessionStart 在壓縮後會不會再觸發沒查到。驗法：Codex 裝好後把對話撐到壓縮，看 agent 有沒有重新載入 duck。不會的話在 `hooks/hooks.json` 加 PostCompact，並確認 Claude Code 對 PostCompact 的輸出也收進上下文。

## Codex 上外掛 hook 的三個未驗證點

`${CLAUDE_PLUGIN_ROOT}` 在 Codex 的 hook 指令裡會不會展開（ponytail 這樣寫並說可用；i-have-adhd 保守地用 `node -e` 讀 `PLUGIN_ROOT`）；第一次載入 hook 是否要在 `/hooks` 按信任；skill 是打 `$duck` 還是帶外掛前綴。三個都在第一次 `codex plugin add` 後看，結果寫回 README 安裝段。

## `.codex-plugin/plugin.json` 的 interface 哪些欄位必填

現在照 ponytail 填了 displayName、shortDescription、longDescription、developerName、category、capabilities、websiteURL、logo、composerIcon。沒查 Codex 文件哪些是必要的。`codex plugin add` 成功就刪這條，失敗就補欄位。

## 兩台機器從舊版換過來

兩台都還是舊版手動安裝（`~/.claude/skills/duck`、`digest`、`~/.agents/skills/` 同名目錄、settings.json 和 `~/.codex/hooks.json` 各一條 hook、`~/.rubberduck/`）。順序：先在 checkout 裡跑 `node skills/unduck/uninstall.mjs --yes` 清舊版，再 plugin install；反過來的話 `/unduck` 會連新版一起移掉。Unfold repo 裡的 `rubberduck/` 目錄、`docs/README.md` 的索引列、`TODO.md` 三條相關項目一併處理。

## hero.png 太大

`assets/hero.png` 1.3 MB，README 開頭就載入它。這台沒有 pngquant、oxipng、ImageMagick、PIL，沒法壓。裝其中一個後把它量化成 256 色 PNG，扁平插畫應該能到 300 KB 以下；README 顯示寬度 800，1600 寬留給高解析螢幕即可。
