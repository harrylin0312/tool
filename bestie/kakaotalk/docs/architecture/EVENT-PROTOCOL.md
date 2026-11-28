# V2 本機事件與一致性變更協定

P2.1 的事件及投影協定版本為 2。Event Log 是輕量變更索引，包含 seq、schema_version、generation、kind、object_id、version、observed_at 和 change。訊息／引用／Threads 的原文在投影，事件只保存欄位名、物件識別、版本及觀察狀態。公開傳輸時應使用無損的十進位序號字串。CLI 是本機私有介面，輸出 JSON 整數。

## 事件水位與資料世代

SQLite 交易同時提交訊息、關係、同步游標和事件。外部見證檔保存資料庫識別、當前世代、最高事件序號、鏈尾指紋與來源同步狀態指紋。更新時先在見證預留預計提交的點，提交 SQLite，再確認見證。重開若資料正好對應預留點便完成確認；其他歧義停止並要求明確還原。見證與資料庫兩者同時回退、或同一使用者帳號改寫受信任的儲存時，無法保證偵測。

以 SQLite Backup API 建立旁路備份。還原檢查備份與見證是同一資料庫家族並核對完整性，將已驗證的副本原子換入，產生新資料世代。新世代初始水位為零，舊事件僅留在本機，不能用舊世代游標讀新世代。生成新世代後的序號可從較高值開始，客戶端按已核對的水位使用，不要求連續整數。穩定物件 ID、書籤映射及備份原有譯文保留。

## 一致性變更批次

`changes --generation G --after S --output FILE` 在一筆讀取交易固定結束水位 E，取出 `(S,E]` 觸及物件的 **最新一致投影**。同一物件連更新三次，輸出一份 E 下的版本與必要關係。每個 object bundle 含物件、引用、討論串成員、目前原文版本譯文。翻譯列表和關係以替換處理。歷史投影或映射異動時，`replace_legacy_and_mappings` 要求整組替換，即使新列表為空。其他物件以 ID upsert。無變更的增量批次可以是空陣列。

批次包含此次請求世代、start、end、目前世代、mode、reset_reason、batch_id 及 records。CLI 將資料寫入 0600 私人檔案。batch_id 是批次內容指紋。page 只讀這個已物化的批次，驗證指紋後依 offset 切頁。後續新交易只會出現在下一批。初始讀取可使用未知／空世代及 0，取得完整投影。世代不符、游標超前或找不到指定水位時返回 mode=snapshot。

客戶端先確認資料來源及世代，並確認本機已提交水位等於同世代增量的 start。收齊同一 batch_id、start、end、generation 和 length 的所有連續頁後，在同一筆客戶端交易中套用物件、關係、歷史資料及結束水位。失敗或漏頁整批重試，已完整提交的批次可辨識後略過。拒絕較本機快取更早的同世代快照。世代變更須經可信的切換程序並以完整快照原子替換；新舊序號不能互相比較。

## 事件種類

- message.created、message.updated 記錄首次觀察或後續變更。歷史匯入／補載帶 historical。
- author.updated、thread.updated 反映獨立原生物件。討論串成員變化亦可經訊息 bundle 取得。
- translation.completed 附訊息 ID、語系與 input_version。譯文本身留在資料庫。
- legacy.projection_updated 與 legacy.mapping_updated 推進歷史或書籤的行為水位。未審核的原始證據不在投影內。
- 撤回語義待實機驗證，原生狀態以 message.updated 表示。

未來批次發布和串流可共享本協定。事件本身不承諾逐事件重建舊正文，本階段也未實作 SSE 或客戶端持久化。
