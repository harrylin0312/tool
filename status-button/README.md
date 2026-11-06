# Shared Status｜共享狀態按鈕

顯示及切換共享的「使用中／未使用」狀態，包含兩小時倒數與狀態同步。

入口：`/tool/status-button/`。

- `index.html`：頁面與 Firebase SDK 載入。
- `script.js`：狀態同步、切換、倒數及過期處理。
- `styles.css`、`icon.png`：樣式與圖示。

資料沿用 Firebase 專案 `using-status` 的 Firestore `shared/status` 文件。搬移未變更資料庫或 localStorage key；同來源的原有瀏覽器資料仍沿用。

在 tool 根目錄執行 `python3 -m http.server 4173`，入口為 `http://localhost:4173/status-button/`。開啟頁面可能初始化或更新共享狀態，開發驗證請留意既有資料。

原始來源為 `harrylin0312/status-button`；本次將網站檔案納入 tool，原獨立儲存庫仍保留。
