# KakaoTalk Reader｜專案入口

更新：2026-11-28（台灣時間）。本文件為現行狀態及文件索引；舊交接已結束，不再以歷史 HANDOFF 的數字或實作順序為準。

## 目標與優先順序

提供指定、已登入的 KakaoTalk Open Chat 的原文、繁中翻譯及可核對的回覆關係，手機可直接開啟私人解鎖網址。GitHub Pages 加密快照是目前可用方式；**下一代優先採用 KakaoTalk 原生資料**。先在平行本機資料庫驗證擷取與同步，同一套模組會供批次發布和未來串流使用。

## V2 開發分支

P2.1 已依獨立 QA 修正事件世代、來源信任、可發布歷史、翻譯輸入版本與一致性投影，待 Work 第二輪驗收。P2 候選基準為 `1071dd72474564cab85bc32b5f49cd49ceb24f5a`。在 `dev/kakaotalk-native-v2` 驗收，正式原文與發布流程仍採 main 的既有版本。新三層架構、CLI 與驗收證據見下表。

## 現況（以實際正式快照與 QA 區分）

| 項目 | 狀態 |
| --- | --- |
| 原文版 | [original/index.html](original/index.html)，發布時的 Mac App 匯出 CSV 為 2,457 列，末筆 2026-11-27 23:27:25；2,459 個訊息／事件 ID，2,027 則一般訊息、432 個有 ID 的事件；214 組雙向回覆、107 個不可跳轉引文。 |
| 韓中對照版 | [index.html](index.html)，較早的 1,380 列 Mac App 匯出 CSV 批次，併入早期介面掃描所得歷史、1,383 個紀錄 ID，截止 11/26 22:44:06；不等同原文版進度。 |
| 原文發布器 | 已合併 main：bda8ae8（第二輪驗收候選 c1bf0c86）。兩輪獨立 QA 已完成；現行正式 HTML 未執行首次來源映射遷移。 |
| QA 隔離副本 | 1,890 個歷史一般訊息映射逐筆核對無誤；137 個未建立可靠映射但保留；第二、三批受控測試後共 218 組雙向回覆、2,465 列。這些新增測試資料未上線。 |
| 手機備援 | 11/28 已成功從 Gmail 原始 MIME 取得 ZIP，解壓及 CRC32 驗證；TXT 不含結構化回覆關係，只有分鐘精度。未實作匯入或發布。 |
| 本機檔案擷取 | R1 原始碼審查與 Mac 檔案探測已完成。R2 已唯讀取得 50 則原生樣本，6 組回覆與快照一致，畫面待補驗。R3 已完成一次原生盤點及 CSV／HTML 差異比對。Threads 已用一串歷史 App 面板核對，R4 已完成原生副本效能與合成 WAL／監聽試驗。實際 App 共用連線及新畫面抽樣待驗。見 [增量研究](docs/research/INCREMENTAL-EXTRACTION-REPORT.md) 及 [第二代設計](docs/research/NATIVE-EXTRACTOR-DESIGN.md)。見 [原生盤點](docs/research/NATIVE-DATA-AUDIT.md) 及 [PoC](docs/research/LOCAL-EXTRACTION-POC.md)。見 [研究報告](docs/research/LOCAL-EXTRACTION-REPORT.md)。 |
| 即時串流 | 最後階段；舊設計僅為候選方案，未完成正式驗收。 |

原生資料、App 匯出、畫面衍生、HTML 與來源未知的檔案各自保存。用於發布或帶有舊回覆標記的資料仍須核對；來源分類見 [增量研究](docs/research/INCREMENTAL-EXTRACTION-REPORT.md#資料來源核對)。

正式發布器上線不代表正式快照已完成遷移；也不代表新手機匯出已匯入。不得拿 QA 的合成資料或舊譯文快照當正式來源。

## 文件分工

| 文件 | 用途 |
| --- | --- |
| [V2 架構](docs/architecture/V2-ARCHITECTURE.md) | Mac 即時、GitHub Pages 與客戶端離線三層，以及共用擷取核心。 |
| [V2 資料模型](docs/architecture/DATA-MODEL.md)／[事件協定](docs/architecture/EVENT-PROTOCOL.md) | Repository、穩定 ID、可重播事件與世代。 |
| [P2 原獨立 QA](docs/research/P2-QA-REPORT.md)／[P2.1 修正](docs/research/P2-QA-REMEDIATION.md) | 五項修正、永久回歸測試、真實副本驗證及剩餘限制。 |
| [V2 本機操作](native-v2/README.md)／[P2 驗收報告](docs/research/P2-IMPLEMENTATION-REPORT.md) | CLI、測試指令、實機副本量測及後續驗收範圍。 |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | 現行擷取、回覆審核、原文及翻譯發布、加密、驗證與回退操作。 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 本機資料庫擷取研究、候選工具、驗證方法與備援。 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 依序開發的里程碑、阻礙、驗收條件、代理分工。 |
| [live/QA-REPORT.md](live/QA-REPORT.md) / [第二輪](live/QA-REPORT-ROUND2.md) | 不改寫的獨立驗收原始報告。 |
| [storage-workflow.md](storage-workflow.md) | 歷史儲存、容量、掃描與本機工作區紀錄；數值有時間範圍。 |
| [live-sync.md](live-sync.md) | 舊串流設計草案，僅在最後階段重新評估。 |
| [HANDOFF.md](HANDOFF.md) | 舊入口相容索引；原始交接已封存於 Git 歷史。 |

## 代理共同工作規則

- 先讀本 README，再讀任務對應文件；以目前 main、快照內容及實際 QA 證據核對，不以聊天記憶作唯一依據。
- 開發與獨立 QA 分離。新功能在測試分支驗證；報告需寫候選 SHA、環境、資料來源、預期／實際、缺陷及未測範圍；經擁有者授權才合併／發布。
- 不改既有解鎖 URL、HTML ID、已確認的回覆或翻譯，除非明確核對且獲授權。明文、金鑰、完整解鎖 URL、原始聊天、OCR 截圖、本機資料庫、憑證不得提交公開 repo。
- 除已授權的隔離 SQLCipher 外，新增第三方工具或權限須另行授權；只研究擁有者授權的指定聊天室，預設唯讀，禁止傳送、刪除、修改訊息或上傳私人資料。
- 每次里程碑完成更新 README 狀態及 ROADMAP；舊 QA 與歷史量測原樣保存。不要將計畫寫成已完成。
