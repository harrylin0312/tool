# Neuromancer｜神經漫遊者閱讀器

中文版入口為本目錄的 `index.html`；英文版位於 `english/index.html`。

| 版本 | 發布路徑 |
| --- | --- |
| 中文版 | `/tool/neuromancer/` |
| 英文版（中文釋義與詞彙級別） | `/tool/neuromancer/english/` |

## 啟動與驗證

在本目錄執行 `npm start`，開啟 `http://127.0.0.1:4173/`；英文版為 `http://127.0.0.1:4173/english/`。

- `npm test`：中文閱讀器內容匯入測試。
- `python3 english/build.py`：英文版資料驗證與頁面建置。
- 中文版程式直接放於本目錄，不再保留重複的 `dist/` 副本。
- 英文版功能與資料說明見 [英文版文件](english/README.md)。

## 搬移說明

原 `quiet-reader/` 與 `quiet-reader-english/` 已整併至本目錄。兩版保留原有 IndexedDB 名稱與書籍 ID，同來源、同瀏覽器的既有資料不因目錄改名而另建資料庫；不同來源或裝置仍需匯出與匯入備份。

中文版 Service Worker 限定處理中文內容，不快取英文子目錄；清理快取時只刪除本閱讀器自己的新版快取。

舊網址不再提供入口；既有書籤與主畫面捷徑應改用新網址。部署狀態以 GitHub Pages 實際發布結果為準。
