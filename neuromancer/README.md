# Neuromancer｜神經漫遊者閱讀器

中文版入口為本目錄的 `index.html`。英文版位於同層的 `neuromancer-en/index.html`。

| 版本 | 發布路徑 |
| --- | --- |
| 中文版 | `/tool/neuromancer/` |
| 英文版（中文釋義與詞彙級別） | `/tool/neuromancer-en/` |

## 啟動與驗證

在儲存庫根目錄執行 `python3 -m http.server 4173 --bind 127.0.0.1`，開啟 `http://127.0.0.1:4173/neuromancer/` 或 `http://127.0.0.1:4173/neuromancer-en/`。

- `npm test`：中文閱讀器內容匯入測試。
- `python3 ../neuromancer-en/build.py`：英文版資料驗證與頁面建置。
- 中文版程式直接放於本目錄，不再保留重複的 `dist/` 副本。
- 英文版功能與資料說明見 [英文版文件](../neuromancer-en/README.md)。

## 搬移說明

中英文閱讀器各有獨立目錄。兩版保留原有 IndexedDB 名稱與書籍 ID，同來源、同瀏覽器的既有資料不因目錄改名而另建資料庫；不同來源或裝置仍需匯出與匯入備份。

中文版 Service Worker 的作用範圍是 `neuromancer/`，並略過舊英文入口。

舊英文網址 `/tool/neuromancer/english/` 會轉到 `/tool/neuromancer-en/`。
