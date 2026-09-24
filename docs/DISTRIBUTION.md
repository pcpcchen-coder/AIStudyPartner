# 獨立 Mac 安裝包

v0.3.2 提供 Apple Silicon（M 系列）Mac 的 DMG。它內附 Python 3.12.13、應用程式及官方公開發行的 Codex 0.156.1；收件者不需下載原始碼，也不需另裝 Python、uv、Node 或 Codex。這是本機 App 啟動器加瀏覽器介面，AI 分析仍需連網與自己的 ChatGPT 帳號。GPT-6 系列 是否可用依帳號權限與額度為準。

## 安裝與使用

1. 退出正在執行的舊版伴讀 App，以免占用 8765 連接埠。
2. 開啟 DMG，將 AIStudyPartner 拖到 Applications，複製完成後退出磁碟映像。
3. 從「應用程式」開啟 AIStudyPartner。App 會開啟本機伴讀網頁並留在 Dock。
4. 使用自己的 ChatGPT 帳號登入、允許瀏覽器使用攝影機。第一次使用仍需主動勾選允許傳送作業；自動讀題預設關閉。
5. 要關閉服務，再點 Dock 圖示並選「關閉服務並退出」，或使用 App 選單「退出」。只關閉網頁不會退出服務。

系統最低版本會依內附執行檔寫入 App 與 DMG 的安裝說明；目前僅在建置機驗證，其他 Mac 與最低版本系統仍待實測。Intel Mac 不適用此安裝包。

## 簽署狀態

目前產出為 **ad-hoc 簽署、未經 Apple 公證的測試版**。它已具備獨立執行環境，但不是可保證下載後直接開啟的正式發行版。其他 Mac 的 Gatekeeper 可能阻擋；不要關閉系統安全檢查。

正式發行需要持有者提供可用的 Developer ID Application 憑證並完成 Apple notarization。Apple Development 憑證不能代替此發行憑證。建置工具支援指定發行憑證與已設定的公證設定；此流程尚未在本專案完成驗證。

## 資料與更新

- 獨立版資料位於 `~/Library/Application Support/AIStudyPartner`，Codex 登入由內附官方程式管理。
- 安裝包不包含作者的 `.runtime`、帳號、金鑰、作業或開發環境。
- 不會搬移／借用原始碼版或其他 Codex 的登入，首次開啟要重新登入。
- 更新前退出 App，再替換 Applications 裡的 App；使用者資料留在原處。
- 移除 App 不會自動刪除登入資料。若要移除帳號，先從伴讀頁面登出，再退出 App；需要完整清除時可另刪上述專屬資料夾。
- 原始碼版的 `Install App.command` 仍是依賴專案位置的開發啟動器，不能拿它取代獨立 DMG 分享。

## 維護者建置

在 Apple Silicon Mac 上，安裝 uv、同步專案依賴後：

```bash
uv sync --frozen --python 3.12
uv run python scripts/build_standalone.py --output /absolute/path/to/empty-release-folder
```

工具從公開來源取得固定版本的 Python 與 Codex 並核對雜湊；只收錄白名單程式檔及鎖定的正式依賴，保留授權資訊，產出 App、DMG、說明及 SHA256SUMS.txt。登入與快取均寫在 App 外部。請勿手動把整個開發專案或 `.runtime` 加到 App。

有可用發行憑證及公證設定後，可加上：

```bash
--identity 'Developer ID Application: Your Name (TEAMID)' --notary-profile 'your-keychain-profile'
```

公證流程需要完成 Apple 工具的授權設定。輸出保存 Apple 的 JSON 回執，只有 Accepted 才會 stapler。正式提供下載前仍須在另一台 Mac 檢驗 Gatekeeper、登入、相機與正常退出。
