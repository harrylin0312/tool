# 靜讀・英文 Quiet Reader English

閱讀網址：https://harrylin0312.github.io/tool/quiet-reader-english/

已完成全書 **24 章（含 Coda）及作者致謝**，涵蓋提供的英文 PDF 第 3–266 頁。沿用 quiet-reader 版面與閱讀功能，加入逐字繁體中文解釋與大考 Level。全部資料離線預載。

| 範圍 | 章節 | 段落 | 英文單字（含重複） |
| --- | --- | --- | --- |
| Part One | 1–2 | 388 | 12,409 |
| Part Two | 3–7 | 511 | 17,029 |
| Part Three | 8–12 | 639 | 16,096 |
| Part Four | 13–23 | 1,009 | 32,096 |
| Coda | 24 | 48 | 1,188 |
| 作者致謝 | 獨立附錄 | 2 | 29 |
| 合計 | 24 章＋致謝 | 2,597 | 78,847 |

共 9,019 種字形，所有正文單字皆有中文解釋。

## 查字與級別

- 範圍內顯示 Level 1–6；衍生、時態或複數變化註明對應詞及級別，並保留詞表 PDF 頁碼。
- 範圍外以淺灰色提示，仍可點選；人名、地名、品牌與代號不捏造級別。
- 複合字如以組成詞對照，會列出個別 Level，不視為整詞的級別。
- 基礎釋義以使用者提供的詞表為主，另補充科幻術語、俚語、專名與語境義。多義詞可列出相關義項，不宣稱每次出現都只有一種意思。
- 特別校正 false suffix matches：Denver 不是 deny，Orly 不是 or，Peter 不是 pet，Tally 不是 tale；rider 對應 ride，而非 rid。
- 新增軟體晶片 microsoft、感官借用者 rider、冬寂 Wintermute 等小說語境解釋。Case 普通名詞／人名、Chin 普通名詞／姓氏、Cutter 行動代號等分開顯示。
- 逐個字母拼出的代碼另行說明；例如 Wintermute 的字母序列，不將其中的 I 解釋成代名詞「我」。
- 中文解釋與級別全部預載，不呼叫線上翻譯 API。尚未建立詞義的匯入書籍使用一般閱讀模式。

## 閱讀功能

保留原版固定頁首、側欄、正文與固定頁尾，以及目錄、前後章、搜尋、書籤、筆記、自動捲動、沉浸、字體排版、四色主題、設定與備份。英文版使用獨立 IndexedDB，沿用既有書籍 ID 以保留閱讀位置與書籤。

各部與 Coda 末尾標示完成；致謝為獨立附錄，不誤列為第 25 章。手機排版將單字與其後標點保留為同一個排版單位，避免句點獨自換行。

## 原文完整性

依 PDF 行距還原段落，接合跨頁句子，清除抽取時的底線強調符號、游離波浪號及斷開的連字號空白。未改寫正文。

各段保留來源頁碼。前兩部已比對單字順序；新增第 99–266 頁共 49,409 個單字與獨立逐頁抽取結果完全一致，移除空白後的全文字元也一致。

## 檔案與建置

- `reader-book.json`、`reader-lexicon.json`：現行全書正文、詞義與來源級別。
- `part-one-book.json`、`part-one-lexicon.json`、`part-two-book.json`、`part-two-lexicon.json`：各階段來源資料。
- `part-one-notes.tsv`、`part-two-notes.tsv`、`remaining-notes.tsv`：補充及校訂釋義，並非全部詞彙資料。
- `template.html`、`app.js`、`style.css`、`english.css`、`content.js`：閱讀器介面與功能。
- `build.py`：驗證章節、全文端點、詞義覆蓋、級別依據與回歸案例，產生發布用 index.html 及 validation.json。
- `sample-data.json`：先前單頁樣本資料，現行建置不再使用。

執行 `python3 build.py`，再以 `python3 -m http.server 4178` 啟動，開啟 http://127.0.0.1:4178/。不需 npm 安裝或外部 API。

## 驗證

已通過建置驗證、9,019 種字形的中文解釋覆蓋、級別來源與易混淆字回歸檢查、JavaScript 語法檢查。瀏覽器逐章確認新增第 8–24 章及致謝的段落和可點選單字數、完整目錄、各部結尾及附錄標籤。保留既有書籍 ID，延續閱讀位置與書籤。未在實體 iPhone Safari 驗證。
