# Mac 安裝與瀏覽器登入

## 安裝與啟動

1. 安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/)。Python 3.12 由 uv 管理，不需要 Xcode。
2. 安裝 [Codex CLI](https://learn.chatgpt.com/docs/cli) 或含 Codex 的桌面版。程式會先找 PATH，或 `/Applications/ChatGPT.app/Contents/Resources/codex`、`/Applications/Codex.app/Contents/Resources/codex`。
3. 下載 Repo，執行 `bash scripts/start.sh` 或雙擊 `Start.command`。
4. 開啟 `http://127.0.0.1:8765`。先用示範模式亦可，不需登入或額度。

可選 `.env` 只放模型、呼叫上限及 Codex binary 路徑；**不要填 API Key**。若使用自訂執行檔，設定 `STUDY_CODEX_BIN=/你的絕對路徑/codex`。

## 官方 OAuth 登入

1. 按伴讀畫面的「登入 ChatGPT」。
2. 程式開啟官方網站；若瀏覽器擋彈出視窗，點「開啟官方登入頁面」。
3. 在官方網站完成登入／MFA，密碼不經過伴讀應用。
4. 回到伴讀頁，按「登入後重新檢查」。看到「已透過 ChatGPT 登入」後再開始。
5. 勾選允許作業傳送，才會實際送圖進行推理。

本專案使用自己的 `.runtime/codex-home`，所以你即使已登入其他 Codex，也可能要在這裡登入一次。這是為了隔離認證與設定；不搬移／複製你現有的 token。後續 token 刷新由官方 Codex 管理。

「已登入」不是模型權限測試。若 Astra 無權限／額度不足，會停止自動分析並顯示錯誤，不改用 API 或其他模型。用量以你的 ChatGPT／Codex 方案為準，不代表無限量。

「結束並清除」清本次作業，保留登入方便下次使用。「登出伴讀帳號」清本專案登入，不影響日常 Codex 帳號。不要把 `.runtime/` 或任何 `auth.json` 分享到 GitHub。

## 相機與陪讀

相機固定於前上方、盡量讓紙面與鏡頭平行，先用 1080p 實測。開鏡頭後拖曳框住單題、作答與必要圖表。手掌、反光、傾斜會降低可讀性。不要把人臉／姓名框進去。

年級和科目切換會重設目前題目。可以修正 OCR 文字，確認後再判讀。兩層提示之後需明確點擊才顯示完整說明與複習。複習題先作答再自己對照參考答案。

「暫停陪讀」停止自動分析及提醒，鏡頭仍本機預覽。「結束並清除」才關鏡頭。離開分頁會暫停自動分析，回來需手動繼續。想保留學習紀錄需結束前匯出 JSON。

## 語音

勾選本機中文語音，僅使用瀏覽器回報 `localService=true` 的中文聲音，優先 zh-TW。找不到就提示安裝，沒有遠端 TTS fallback。請先在 macOS 語音／輔助使用設定下載中文聲音；實際支援依瀏覽器與系統資產而異。

## 排錯

| 問題 | 處理 |
|---|---|
| 找不到 Codex | 安裝 CLI／桌面版，或設定 STUDY_CODEX_BIN；不要使用 App Translocation 臨時路徑 |
| 登入網址不出現 | 檢查 Codex 版本、localhost callback 埠是否被占用，稍後重試登入 |
| 已登入但模型失敗 | 確認方案、模型權限與額度；不切換 API Key |
| 鏡頭無畫面 | 瀏覽器權限、macOS 隱私權與安全性、USB 接線、是否被其他程式占用 |
| 只看到內建相機 | 開過權限後，在「鏡頭與陪讀設定」切換 webcam |
| 自動看題沒觸發 | 需雲端開關、有新變化、穩定 2 秒、滿間隔；編輯文字時暫停自動更新 |
| 沒有即時提示 | 若模型還在推理，只能先給一般引導；不能承諾雲端低延遲 |
| 修改後無法看解答 | 人工確認失效，重新確認文字 |
| 顯示忙碌 | 一次只推理一題，等在途請求完成 |
| 達呼叫上限 | 先查方案用量再決定是否重啟；重啟只重設本機計數，不重設方案額度 |

相機只在 localhost 等安全來源可用。[MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。第一版只供 localhost，不能用公開 tunnel 當多人服務。
