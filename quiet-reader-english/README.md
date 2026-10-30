# 靜讀・英文 Quiet Reader English

線上閱讀：https://harrylin0312.github.io/tool/quiet-reader-english/

已完成使用者提供之 Neuromancer 英文 PDF 的 **Part One — Chiba City Blues**，共兩章，涵蓋原 PDF 第 3–42 頁。沿用同儲存庫 quiet-reader 的版面與閱讀工具，加入點字中文解釋與大考 Level。Part Two 起尚未加入。

## 內容與查字

- 兩章共 388 段、12,409 個英文單字（含重複），涵蓋 3,041 種字形；所有正文單字皆有繁體中文解釋。
- 詞表內字顯示 Level 1–6；詞性衍生、時態與複數變化標示對應詞與級別，並提供詞表 PDF 頁碼。
- 詞表外使用淺灰色，仍可點選；人名、地名、品牌另行說明，不捏造級別。
- 複合字若以組成詞對照，會列出組成詞的 Level，不把它當作整詞的級別。
- 基礎釋義取自使用者提供的詞表；另補充小說的科幻用語、俚語、專名及語境義。多義詞可顯示相關義項，不宣稱每次出現都只有單一意思。
- 不規則變化與易混淆詞已複核，例如 found→find、dying→die、faded→fade、cubes→cube；Case 人名與 case 普通名詞使用不同解釋。
- 詞義與級別全部預載，不使用線上翻譯 API；自行匯入且未建立詞義的書籍仍使用一般閱讀模式。

## 閱讀功能

保留原版固定頁首、左側工具、章節標記、正文與固定頁尾。支援目錄、前後章、搜尋、書籤、筆記、自動捲動、沉浸、字體排版、四色主題、偏好與備份。英文版使用獨立 IndexedDB。

沿用既有英文樣本的書籍 ID，更新後替換成完整 Part One，保留原本第一章的閱讀位置及書籤。第二章結尾標示「Part One 完」，不顯示「全書完」。

## 來源整理

章節 1 始於 PDF 第 3 頁，結束於第 28 頁；章節 2 自第 28 頁開始，結束於第 42 頁。第 43 頁是 Part Two，未加入。依 PDF 的行間距還原段落，接合跨頁句子。清除 PDF 的底線強調符號與游離波浪號，接回六處被空白斷開的連字號，修復一處被拆開的 You're；沒有改寫正文。

獨立比對整理後正文與原 PDF 抽出的單字序列：12,409 個單字依序一致。保留 paragraphPages 等來源頁資訊，以利後續核對。

## 檔案

- `index.html`：含預載正文與詞義的發布頁面。
- `template.html`、`app.js`、`style.css`、`english.css`、`content.js`：閱讀器架構、樣式、互動與匯入功能。
- `part-one-book.json`：Part One 兩章正文與段落來源頁。
- `part-one-lexicon.json`：詞義、詞性、詞族與 Level 依據。
- `part-one-notes.tsv`：補充及校訂釋義；不是全部詞彙資料。
- `sample-data.json`：保留先前單頁版本的資料，現行建置不再使用。
- `validation.json`：建置產出的覆蓋率與完整性檢查結果。
- `build.py`：驗證正文、詞義、級別與回歸案例，重建 index.html。

本機執行 `python3 build.py`，再以 `python3 -m http.server 4178` 啟動，開啟 http://127.0.0.1:4178/。不需 npm 安裝或外部 API。

## 驗證

已通過全文單字序列比對、詞義與級別覆蓋檢查、JavaScript 語法檢查；瀏覽器確認第一章 222 段／8,124 個單字按鈕、第二章 166 段／4,285 個按鈕、兩章目錄、章節切換、Part One 結尾、重新載入後章節保存、查義卡與 390×844 手機排版。未在實體 iPhone Safari 驗證。
