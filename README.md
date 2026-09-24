# AIStudyPartner｜AI 伴讀機器人

**Mac ＋ Webcam ＋ GPT-6 系列：看作業、陪思考、給提示，再用複習題確認理解。**

鏡頭放在學生前上方，對準紙本作業。Mac 在本機等待穩定畫面；GPT-6 系列 讀題、解釋、提示與出複習題。每題教學持續保留，直到學生主動按「我理解了，下一題」。支援年級切換及數學、國語、英文、自然、社會等科目。

## 登入方式：ChatGPT 網頁認證，沒有 API Key

點 **「登入 ChatGPT」** → 開啟官方認證網頁 → 完成登入 → 回到伴讀頁面。

本專案透過官方 **Codex App Server** 使用 ChatGPT 登入與 GPT-6 系列，不直接呼叫 OpenAI Platform API，不要求 API Key，也不擷取 ChatGPT 網頁 Cookie。這使用 ChatGPT／Codex 方案額度，模型權限與速率依帳戶為準。

> **狀態：v0.1 可執行原型。** 已完成本機 Codex 握手、未登入狀態查詢及官方 OAuth 登入網址產生驗證；尚未完成本專案的真人 OAuth 登入、AI 真實推理、實體 webcam／手寫作業與中文語音驗收。[驗證詳情](docs/VALIDATION.md)

![示範操作畫面](docs/assets/demo-desktop.png)

## 專案規劃

- [產品規劃與多科目教學](docs/PRODUCT_PLAN.md)
- [系統架構與資料流程](docs/ARCHITECTURE.md)
- [開發階段與工作清單](docs/ROADMAP.md)
- [Mac 安裝、登入與操作](docs/MAC_SETUP.md)
- [資料與隱私](docs/PRIVACY.md)
- [方案額度與延遲規劃](docs/COST_AND_LATENCY.md)
- [測試報告與實機驗收](docs/VALIDATION.md)

## 快速啟動

安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/) 及 [Codex](https://learn.chatgpt.com/docs/cli)。已有 Codex／ChatGPT 桌面版時，程式也會尋找內附的 Codex 執行檔。

```bash
git clone https://github.com/pcpcchen-coder/AIStudyPartner.git
cd AIStudyPartner
bash scripts/start.sh
```

開啟 **http://127.0.0.1:8765**。示範模式不需登入、不會呼叫模型；執行應用程式不需要 Node、Xcode 或 Docker。

### 獨立安裝包（分享給朋友）

v0.3.1 的 Apple Silicon DMG 內附 Python 與官方 Codex，不依賴原專案。開啟 DMG 後把 App 拖到 Applications 即可安裝；朋友使用自己的 ChatGPT 帳號登入。目前為 **未經 Apple 公證的測試版**，其他 Mac 可能被 Gatekeeper 阻擋。[安裝與發行說明](docs/DISTRIBUTION.md)

### 從原始碼建立 Mac App 啟動器

1. 雙擊 `Install App.command`，安裝到 `~/Applications/AIStudyPartner.app`。
2. 從「應用程式」或 Spotlight 搜尋 **AIStudyPartner** 並開啟；App 會啟動本機服務、開啟伴讀網頁並留在 Dock。
3. 再點 Dock 圖示，選「開啟伴讀網頁」或「關閉服務並退出」。也可在 App 的控制對話框選「繼續執行」後，使用 App 選單「退出」或 Command-Q。
4. 下次直接開啟 App；`Start.command` 也會啟動此 App，尚未安裝時會先建立。

這是使用目前專案與 Python 環境的**本機啟動器**，請保留專案資料夾原位置；不是可單獨拷貝到其他 Mac 的完整安裝包。更新 App 前先退出，再執行 `Install App.command`。不建立登入項目、不設定開機自動啟動；關閉網頁不會關閉 App。詳見 [Mac 設定](docs/MAC_SETUP.md#mac-app-的安裝啟動與退出)。

### 選擇伴讀模型

「伴讀模型」下拉選單提供 GPT-6 Astra、GPT-6 Sol、GPT-6 Luna。首次維持原預設，之後記住此瀏覽器的選擇。切換後下次辨識與教學使用新模型，已有提示、說明及複習作答保留；處理中暫時不能切換。帳號無權限或額度不足時顯示錯誤，不自動改用其他模型。

### 真實作業陪讀

1. 按「登入 ChatGPT」，在官方網站登入；回到頁面按「登入後重新檢查」。
2. 選年級／科目、開啟鏡頭，框選**一題＋作答＋必要圖表**，避開姓名和人臉。
3. 勾選「允許傳送作業至 OpenAI 進行分析」。這才啟用雲端看題。
4. 核對辨識結果，必要時改字；按「文字正確，幫我看看」。
5. 先看提示，需要時再看完整解釋與複習題。「我再想一下」延後提醒兩分鐘。
6. 讀題後，揮手、書寫、翻轉鏡頭或改框選都不會清掉本題教學。理解並完成練習後，按「我理解了，下一題」才清空並讀取下一題；切換年級／科目也在這時進行。
7. 結束可主動匯出不含圖片的 JSON 紀錄；「結束並清除」停止鏡頭與清除本次學習狀態。

原始碼版登入由本專案獨立的 `.runtime/codex-home` 管理（獨立安裝版改存於 `~/Library/Application Support/AIStudyPartner/codex-home`），不借用或改寫你平常 Codex 的登入與設定。登出伴讀帳號也不登出日常 Codex。認證儲存由官方 Codex 的 OS keyring／本機 auth 機制處理，**不要分享 `.runtime/`**。

`.env` 僅供選用設定，無任何金鑰：

```dotenv
STUDY_MODEL=gpt-6-astra
STUDY_MAX_CALLS=120
```

## 已實作

- 攝影機選擇、左右／上下翻轉、還原方向、ROI 框選；預覽、截圖與停筆偵測方向一致，JPEG 長邊最多 1600 px。
- 0.5 秒本機取樣，尚未讀題時穩定 2 秒可自動讀取一次；本題鎖定後，畫面變動只影響活動／停筆偵測，不重新辨識。
- 20／30／60 秒停筆提醒、60 秒冷卻及兩分鐘延後；現階段為畫面活動估計，尚非筆尖追蹤。
- GPT-6 系列 讀題、結構化教學、兩層提示、完整解釋、1–3 題複習。
- 可更正辨識文字；未確認或不確定不判正誤。純四則式使用有理數核算，其他標示 AI 建議。
- Mac 已安裝的本機中文語音；不自動切成雲端語音。
- 辨識、提示與完整說明處理中顯示全頁遮罩、目前階段與等待秒數，完成／失敗自動收起；可取消等待並保留本題。
- 單一併發、每次啟動最多 120 次模型請求、用量顯示、錯誤停止自動呼叫。
- 六科人工示範，與真實 AI 結果明確區分。
- OAuth 瀏覽器登入、狀態檢查、專案帳號登出；無 API Key fallback。

## 尚未完成

真實模型與手寫品質驗收、可靠的全頁自動追題、筆尖追蹤、透視校正、跨日個人化記憶、間隔複習排程、課綱知識庫、語音問答、Developer ID 簽署與 Apple 公證、家長儀表板。年級選項會影響 prompt，但尚無逐年級驗證資料集。複習題目前由學生自行對照參考答案，不自動評分。

## 開發與測試

```bash
uv sync --frozen --python 3.12
uv run ruff check .
uv run pytest -q
npm ci
npm test
npx playwright install chromium
npx playwright test
```

測試使用合成圖、固定教材及模擬 Codex 協定，不需登入或消耗方案額度。正式啟用前依[驗收表](docs/VALIDATION.md)完成真實測試。

## 官方依據

[Codex 瀏覽器登入](https://learn.chatgpt.com/docs/auth) · [App Server 整合與 OAuth](https://learn.chatgpt.com/docs/app-server) · [GPT-6 系列模型](https://developers.openai.com/api/docs/guides/latest-model)

查核日期：2026-09-23。使用者方案、模型可用性與資料政策仍以實際帳號為準。
