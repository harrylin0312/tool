# V2 本機資料模型

單一旁路 SQLite 對應一個唯一匹配的 Open Chat。Schema 以 `PRAGMA user_version` 與私有格式標記驗證，逐版移轉由本機交易保護。版本 1 建表，版本 2 加索引，版本 3 加獨立舊來源資料與原始檔身分欄。

| 表 | 意義 |
| --- | --- |
| objects | 訊息、作者和 Threads 的最新正規化狀態。物件 ID 由房間、類型、原生 ID 確定性產出，物件版本單調增長。 |
| sources | 每個物件目前採用的原生觀察、來源世代及原始欄位。更舊的外部來源在 legacy_records 各自保留。 |
| replies | 回覆端的物件 ID、目標原生 ID、引用當下預覽及解析證據。目標正文從該房間的訊息另查。找不到目標時保留預覽。 |
| thread_members | 原生 threadId 與訊息的關係，無串中繼紀錄時仍保留成員。Thread 記錄保留來源計數及串尾，計數與可讀成員可不同。 |
| translations | 每則訊息、語系、原文版本各自保存。舊版本不蓋掉現在的原文。 |
| legacy_records、legacy_assertions | App 匯出、畫面衍生、HTML 或未知來源的歷史證據與人工確認的映射。相同舊 ID 有多個不同候選時回報歧義。 |
| sync_state、metadata | 本機世代、來源世代、來源檔案身分、封存時間、高水位與最後完整對帳。 |
| events | 與投影狀態及游標一同提交的可重播事件。 |

原生 ID 以 SQLite 整數查詢、十進位字串輸出。事件類型、scope、status、revision、subType、contentFlag 保留原始值。事件正文以原生訊息欄位保存。遇到無法解析的引用附件會保存附件及 unparsed 狀態。本地投影將未經實機確認的語義交給後續驗收。來源查不到的紀錄保留原文並標示 not_observed，不據此判定撤回。舊來源匯入與審核映射是可呼叫的本機 repository 介面，尚未批量移轉歷史或翻譯。
