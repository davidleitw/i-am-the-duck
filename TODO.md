# TODO

只放還沒做的事。做完就整條刪掉，`git log` 才是歷史。每條自成一體：問題是什麼、在哪個檔、做完長什麼樣。

## Codex 壓縮後會不會重新提醒

Claude Code 在對話壓縮後會以 `source: "compact"` 再跑一次 SessionStart，`hooks/hooks.json` 的 matcher 有列 compact。Codex 另有獨立的 `post_compact` 事件，SessionStart 在壓縮後會不會再觸發沒查到。驗法：Codex 裝好後把對話撐到壓縮，看 agent 有沒有重新載入 duck。不會的話在 `hooks/hooks.json` 加 PostCompact，並確認 Claude Code 對 PostCompact 的輸出也收進上下文。

## Codex 上外掛 hook 還沒驗證

2026-09-05 這台的 Codex 是手動把 repo clone 進 `~/.codex/plugins/cache/i-am-the-duck/i-am-the-duck/0.0.1/` 並在 config.toml 加 `[plugins."i-am-the-duck@i-am-the-duck"]`，因為 repo 私有、`codex plugin add` 走 https clone 會失敗。skill 已被認出（`codex exec` 看到 `i-am-the-duck:duck`），但 hook 在 `/hooks` 按信任前會被跳過，所以還沒看到它送提示。待辦：在 Codex 裡打 `/hooks` 信任 hook，開新 session 看第一句前有沒有載入；`${CLAUDE_PLUGIN_ROOT}` 在 Codex 的 hook 指令裡會不會展開也在這一步才知道。repo 公開後把手動放的那份拆掉（`codex plugin remove`，不行就刪快取目錄和 config 那段），改用 `codex plugin marketplace add davidleitw/i-am-the-duck` 加 `codex plugin add` 正式裝一次。

## `.codex-plugin/plugin.json` 的 interface 哪些欄位必填

現在照 ponytail 填了 displayName、shortDescription、longDescription、developerName、category、capabilities、websiteURL、logo、composerIcon。手動放進快取後 `codex plugin list` 讀得出名字和版本，但 `codex plugin add` 沒真的跑過，它的驗證可能更嚴。正式裝一次成功就刪這條。

## 另一台機器從舊版換過來

這台 2026-09-05 已換完。另一台還是舊版手動安裝。順序：clone 這個 repo，先跑 `node skills/unduck/uninstall.mjs --yes` 清舊版（會刪 `~/.claude/skills/duck`、`digest`、`~/.agents/skills/` 同名目錄、兩個設定檔裡的 hook、`~/.rubberduck/`），再照 README 裝。Unfold repo 裡的 `rubberduck/` 目錄、`docs/README.md` 的索引列、Unfold `TODO.md` 三條相關項目一併處理。

## hero.png 太大

`assets/hero.png` 1.3 MB，README 開頭就載入它。這台沒有 pngquant、oxipng、ImageMagick、PIL，沒法壓。裝其中一個後把它量化成 256 色 PNG，扁平插畫應該能到 300 KB 以下；README 顯示寬度 800，1600 寬留給高解析螢幕即可。

## skill 短名稱能不能用

兩台主機都把 skill 列成 `i-am-the-duck:duck`（Claude 用 `claude -p`、Codex 用 `codex exec` 各問過一次，2026-09-05）。互動時打短名 `/duck`、`$duck` 能不能直接叫到還沒試。能的話把 README 兩份和 `hooks/session-start.mjs` 的提示改短。
