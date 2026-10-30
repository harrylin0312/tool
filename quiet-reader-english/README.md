# 靜讀・英文 Quiet Reader English

閱讀網址：https://harrylin0312.github.io/tool/quiet-reader-english/

目前已完成 **Part One（第 1–2 章）及 Part Two（第 3–7 章）**，涵蓋使用者提供的 Neuromancer 英文 PDF 第 3–98 頁。沿用同儲存庫 quiet-reader 的版面與閱讀功能，加入逐字繁體中文解釋與大考 Level。

依使用者「階段性停止提醒我」的要求，本次在 Part Two 完成、驗證並上線後停止。下一階段是 Part Three，須等使用者要求繼續；不會背景自動執行。

## 完成範圍

| 階段 | 章節 | PDF 頁碼 | 段落 | 英文單字（含重複） |
| --- | --- | --- | --- | --- |
| Part One | 1–2 | 3–42 | 388 | 12,409 |
| Part Two | 3–7 | 43–98 | 511 | 17,029 |
| 合計 | 1–7 | 3–98 | 899 | 29,438 |

涵蓋 5,488 種字形，所有正文單字皆有中文解釋。Part Three 自 PDF 第 99 頁開始，尚未加入。

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

章節 2、章節 7 分別標示 Part One 完、Part Two 完，不把已收錄內容誤稱為全書。手機排版將單字與其後標點保留為同一個排版單位，避免句點獨自換行。

## 原文完整性

依 PDF 行距還原段落，接合跨頁句子，清除抽取時的底線強調符號、游離波浪號及斷開的連字號空白。未改寫正文。

Part One 的 12,409 個單字、Part Two 的 17,029 個單字，均已與另一份 PDF 逐頁抽取結果比對，單字及其順序完全一致。各段保留來源頁碼。

## 檔案與建置

- `reader-book.json`、`reader-lexicon.json`：現行七章正文、詞義與來源級別。
- `part-one-book.json`、`part-one-lexicon.json`、`part-two-book.json`、`part-two-lexicon.json`：各階段來源資料。
- `part-one-notes.tsv`、`part-two-notes.tsv`：補充及校訂釋義，並非全部詞彙資料。
- `template.html`、`app.js`、`style.css`、`english.css`、`content.js`：閱讀器介面與功能。
- `build.py`：驗證章節、全文端點、詞義覆蓋、級別依據與回歸案例，產生發布用 index.html 及 validation.json。
- `sample-data.json`：先前單頁樣本資料，現行建置不再使用。

執行 `python3 build.py`，再以 `python3 -m http.server 4178` 啟動，開啟 http://127.0.0.1:4178/。不需 npm 安裝或外部 API。

## 驗證

已通過全文單字序列比對、5,488 種字形的中文解釋覆蓋、級別來源與易混淆字回歸檢查、JavaScript 語法檢查。瀏覽器逐章確認 Part Two 的 119／125／85／47／135 段與 3,650／5,019／2,805／1,449／4,106 個可點選單字，以及七章目錄、Part Two 結尾、重載後進度保存、專名與 Level 查字、390×844 手機排版。第三章渲染後全文與來源文字的 SHA-256 一致。未在實體 iPhone Safari 驗證。
