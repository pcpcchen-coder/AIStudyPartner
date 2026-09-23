# 作業資料與登入憑證

本專案採 ChatGPT 瀏覽器認證＋Codex App Server，不使用 OpenAI Platform API Key，因此不能套用 API 模式的 `store=false` 或 API 計費／保留政策來宣稱資料保護。

## 資料會到哪裡

- 相機完整畫面在 Mac 預覽；只把選定的作業區域重新編碼後傳給本機後端。
- 開啟雲端分析後，裁切 JPEG、選定年級／科目、題目和作答送給官方 Codex 引擎，再由 ChatGPT 認證的服務處理。
- 不錄製完整影片、不開麥克風、不做人臉辨識；框選不能自動保證避開姓名或人臉，使用者需確認。
- 文字語音只選本機已安裝的中文聲音。
- 除了使用者主動匯出的 JSON，伴讀程式不將原圖或作業寫入永久檔案。

## OAuth 與保存

官方 Codex 處理瀏覽器登入、callback、token 保存與刷新。程式不解析、不匯出、不把 token 傳到前端。專案 runtime 與日常 Codex 隔離；runtime 權限 0700，且被 gitignore 排除。憑證可能位於 OS credential store 或 `.runtime/codex-home/auth.json`，都不可分享。

推理 thread 使用 ephemeral，history persistence=none；伴讀服務的教學快取最多 16 題，15 分鐘邏輯 TTL，後續請求才清過期內容。這不代表完全不留任何 metadata：Codex 可能保存認證與診斷狀態，OS 也可能 swap。雲端保留與使用政策取決於 ChatGPT 方案、工作區管理和資料控制設定。

[官方認證說明](https://learn.chatgpt.com/docs/auth) 說明 ChatGPT 登入與 API Key 模式適用不同權限與資料處理控制。請勿把「無 API Key」理解為「完全離線」或「雲端零保留」。

## 清除與登出

- **結束並清除**：停止攝影機、清瀏覽器作業及學習紀錄、清本機後端教學快取；不登出帳號。
- **登出伴讀帳號**：官方帳號登出 RPC，另清教學快取。不會影響日常 Codex 的獨立登入。
- 本機清除不能撤回已送到雲端的內容，也不能保證取消已開始的推理或還原額度。
- 手動匯出的 JSON 由使用者自行保存／刪除，可能包含學生作答。

正式兒童試用前，需確認監護人同意與工作區資料設定。第一版沒有多學生權限、兒童獨立帳號或公開服務隔離；由成人設定的可信任本機環境使用。
