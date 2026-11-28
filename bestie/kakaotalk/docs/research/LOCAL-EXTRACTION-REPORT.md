# P1｜Mac 本機資料唯讀擷取研究

2026-11-28（台灣時間）。R1 已完成三個指定候選的靜態審查，R2 已完成 Mac 環境及檔案探測。**目前不能判定指定 Open Chat 能否直接取出結構化資料**。兩個候選有解析原生引用目標的實作，三者均未找到可驗證的獨立討論串關係讀取路徑。

## 候選比較

三個固定版本的專案本體均採 MIT 授權。以公開原始碼和依賴清單核對，測試碼所用的資料及作者註解均只作為各自的證據，未執行候選套件或安裝腳本。

| 候選 | 原始碼證據 | 依賴、權限與網路行為 |
| --- | --- | --- |
| [kakao-mcp @ 028588f](https://github.com/Jaeha0526/kakao-mcp/tree/028588f447536ae4f9b06f54dbf2c876246292cc) | Python 透過 runner 呼叫 kakaocli fork。訊息輸出將 log ID 轉字串，秒級時間轉 KST，回覆解析附件的 src_logId、src_message，引用最多 200 字，並可判定是否引用自己。公開訊息輸出提供暱稱，沒有直接給出作者 ID。視圖包含刪除類型，對指定房間的實際涵蓋未知。 | Python ≥3.10、MCP 2.x、uv.lock。安裝腳本另取得 fork 和 kmsg。文件列出讀取容器可能需完整磁碟存取，發送路徑使用獨立工具與閘門。文字輸出會進入 MCP 客戶端，媒體有獨立取回路徑。 |
| [kakaotalk-mcp-korea @ 5861a6a](https://github.com/gayratjon-02/kakaotalk-mcp-korea/tree/5861a6adec2e5e484530b2e1df0588c9bc1ed305) | 唯讀開啟資料庫，檢查 SQLCipher 3/4。chat-repository 從 NTChatMessage 取 logId、chatId、authorId、sentAt、message、type 和 attachment。依房間 linkId 尋找 Open Chat 暱稱，再回退一般暱稱。附件解析保留 64 位引用 ID 的字串，展示引文最多 80 字。以同房間隱藏撤回事件判定刪除並遮住正文，這項對應尚未在本機證實。 | macOS 13+ 為文件要求，Node ≥22。依賴 MCP SDK、better-sqlite3-multiple-ciphers、plist、zod。postinstall 會建置原生 helper。stdio 本身是本機傳輸，媒體／個人圖片工具會發 HTTP 請求，亦有送出、訊息操作和跨聊天室查詢。文件提及完整磁碟存取及輔助使用權限。 |
| [kakaocli @ 8b6ffcf](https://github.com/silver-flight-group/kakaocli/tree/8b6ffcfdaebc592a735dc1a8bd5e50037e626406) | DatabaseReader 用 SQLITE_OPEN_READONLY，嘗試 SQLCipher 3/4，讀取 logId、chatId、authorId、sentAt、message 等。一般 messages 查詢暱稱 join 限 linkId=0，Open Chat 身分可能缺失。另有增量 watcher，普通訊息輸出沒有可確認的引用或 Threads 關係。 | Swift 6、macOS ≥14、Swift ArgumentParser、系統 SQLCipher，Swift 依賴有 Package.resolved。同步功能有 URLSession webhook，另有介面自動化及 Keychain 登入功能。資料讀取模組與整套 CLI 的權限需求不同。 |

程式碼索引：[Python 引用與欄位](https://github.com/Jaeha0526/kakao-mcp/blob/028588f447536ae4f9b06f54dbf2c876246292cc/src/kakao_mcp/messages.py#L178-L213)、[TypeScript 訊息查詢與刪除判定](https://github.com/gayratjon-02/kakaotalk-mcp-korea/blob/5861a6adec2e5e484530b2e1df0588c9bc1ed305/src/libs/database/chat-repository.ts#L17-L119)、[Swift 唯讀連線與訊息查詢](https://github.com/silver-flight-group/kakaocli/blob/8b6ffcfdaebc592a735dc1a8bd5e50037e626406/Sources/KakaoCore/Database/DatabaseReader.swift#L18-L156)。

秒級欄位有原始碼支持，實機應核對單位、時區及缺值。引用附件可提供預覽，完整被引正文仍須在同房間用目標 ID 查得並檢查可見性。獨立 Threads、加入／離開及管理員隱藏的完整分類均未確認。已知撤回旗標與撤回事件不能推論所有刪除類型。兩個 MCP 的資料庫路徑和 kakaocli 有共同來源，不能視為三次獨立驗證。

## Mac 實測與比較基準

- Apple Silicon arm64，macOS 27.0（26A428），KakaoTalk 26.10.0。環境中 PATH 未找到 sqlcipher。未更改權限、安裝套件或執行候選。
- 在 KakaoTalk 容器中唯讀檢查候選主檔的前 16 bytes 和檔案大小。主檔 2,144,256 bytes，標頭與標準 SQLite 不符；對應 WAL 1,073,184 bytes，SHM 存在。這只證明存在候選檔及附屬檔，無法單靠檔頭確認加密格式、相容模式、房間資料或副本一致性。此次檢查沒有複製或開啟可寫資料庫連線。
- 以 Python 解析既有正式 CSV，核對 2,457 筆、42 筆缺時間，末筆 2026-11-27 23:27:25。原文快照以專案既有 QA 的 2,459 個 ID、214 組雙向回覆、107 個不可跳轉引文為基準。本次沒有重新解密核對快照。
- 沒有取得任何指定房間的原生資料列。原生欄位涵蓋率、正確性、缺漏、重複、擷取時間與資源用量皆未量測，不能將基準筆數當作擷取結果。

## 推薦技術與驗收

1. 若有受支持的受權唯讀存取方式，採單一房間專用的本機離線讀取器。優先參考 TypeScript 候選的房間身分映射、精確 ID 及回覆欄位，保留 Swift 候選的唯讀開啟思路。避免把整套 MCP、媒體下載、傳送或 webhook 帶入實驗。MCP 客戶端可能將輸出交給遠端模型，實驗只輸出 aggregate 數字及錯誤分類。
2. 先確認本機版本相容與一致性。只取主檔可能遺失 WAL 內資料，先後拷貝活動中的主檔與 WAL 也不能保證一致。以可一致讀取的交易或離線一致副本驗證，房間選擇須唯一，所有正文與引用查詢在資料層限定該房間。限制未滿足就停止，保留官方 CSV 工作流程。
3. 先取少量已知樣本，再以同段 CSV 和快照驗證。以序列、時間、作者及原文定位，重複候選保留歧義。報告分開計算唯一對應、漏列、重複、錯連、已知而未解析及超出留存範圍；214 組參考集並非所有回覆。專測同秒重複、跨日和跨批回覆、找不到的原訊息、系統事件及獨立 Threads。原生 ID 全程用無損字串。
4. 同範圍量測首批及增量的冷／暖耗時、峰值記憶體、重跑和重啟。確認分頁邊界與重疊，另外驗證舊訊息編輯或撤回可能無法靠新 ID 游標捕捉。保留既有 HTML ID。R3、R4 完成後再決定可否取代畫面取證。

**決策**：R1 有候選方向，R2 在資料存取環節未通過，R3/R4 待測。維持現行批次流程與正式快照，待確認單房間唯讀存取後再進原生資料 PoC。
