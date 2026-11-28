# KakaoTalk Reader V2 P2 獨立驗收

日期 2026-11-28（台灣時間）。分支 `dev/kakaotalk-native-v2`，候選 `d7e6a0bd4682d648771d26e951fa5b3d3e819d4b`，比較基準 `1071dd72474564cab85bc32b5f49cd49ceb24f5a`。

**P3 可先做隔離原型，暫緩將 P2 契約定為正式快照來源。** 優先釐清舊副本重新封存、舊旁路備份還原及快照對歷史資料的涵蓋範圍。P5 上線前另須明訂事件如何取得一致投影。

## 環境與範圍

Linux x86_64、Python 3.12.14、標準庫 SQLite 3.53.1。先閱讀 native-v2 README、實作報告、架構、資料模型、事件協定及全部核心程式，再重跑測試。比對固定 SHA 與 main 基準，既有網頁與發布器沒有差異。正式測試以候選版本原檔執行。

本環境無法取得授權的 Mac 原生副本。真實聊天室的端到端、App 並行與實際擷取延遲均未測。所有資料均為合成，未使用 OCR 或 CSV 作原生驗證。未直接連線正式 App。

## 獨立情境與架構發現

| 案例 | 預期、重現與實際結果 |
| --- | --- |
| 匯入、增量、分頁與隔離 | 在兩個房間加入相同原生 ID，目標房間包含同秒、相鄰且大於 2^53 的 ID，最後補到 2^63−1。以一列分頁匯入，檢查全部 ID 原樣輸出、另一房間排除、引用與 Threads 由原生 ID 串接。重啟旁路連線後追加新高 ID、低 ID 及舊狀態變更。增量只讀到新尾端，完整對帳補齊低 ID 和舊更新，重跑無新事件。**通過。** |
| 交易、程序與競爭 | 先保留資料、事件及游標，再由子程序執行完整對帳。持有寫入交易時第二程序回報鎖定。釋放後，讓子程序在已寫入、等待來源末端確認時以 os._exit(73) 結束。重新檢查資料、事件水位及同步狀態均維持舊值，SQLite 完整性通過。**通過。** |
| 損毀、過期及來源世代 | 封存後修改複本，雜湊核對在載入驅動前拒絕。舊時間戳副本拒絕，同世代舊上界由正式測試覆蓋。新來源世代的普通同步拒絕，明確核准同房間完整對帳後成功，旁路世代與物件 ID 保留。**通過既有拒絕條件。** 重新封存舊位元組見 V2-05。 |
| V2-01 事件與快照 | 連續把同一則訊息的狀態更新三次，事件可依序取回 v2、v3、v4 及欄位名，資料庫快照只提供 v4。P2 能提供原子快照水位與可分頁的失效通知，但無法逐事件重建歷史內容。**中，協定缺口。** P3 應以同一次讀取的完整投影與水位製作快照。P5 須採版控投影或以一致水位取得批次最新投影，原子套用後再提交游標。未測串流、遠端授權、區塊完整性或序號字串化。 |
| V2-02 舊來源獨有訊息 | 以 preserve_legacy 加入只有舊來源才有的訊息，關閉後重開可在 legacy_records 找到；相同 payload 重跑維持單筆，由正式測試覆蓋。保存時事件水位不變，快照未包含 legacy_records。映射仍能獨立保存與查詢。**高，若 P3 要承接完整歷史則會漏訊。** 定義可匯出的歷史投影與版本事件，保留私有證據和顯示欄位的邊界。 |
| V2-03 非正文變更與譯文 | 為 v1 加翻譯，只改 status，對帳後正文相同但物件成為 v2。譯文仍保留在 v1，以目前訊息版本連接會找不到它，對 v1 提交譯文也被拒絕。**中。** 建議用獨立正文版本或正文摘要關聯譯文，物件版本繼續涵蓋其他欄位與關係。 |
| V2-04 還原舊旁路備份 | 以 SQLite Backup API 留存早期資料，寫入後續事件，另開備份模擬還原。世代相同、水位下降，超前游標暫遭拒絕。從還原本重新對帳，實測重用已發出之序號，對應事件內容不同，水位追上後舊游標又被接受。**高，快取可能靜默分岔。** 正式還原須啟用新資料世代，或以可驗證的事件歷史識別強制重新同步。 |
| V2-05 封存副本 | capture 不經 SQLite 開啟來源，複製前後核對主檔/WAL 狀態及 SHA-256，複本核對後獨立封存。SQLCipher 以唯讀及 query_only 查隔離副本，寫入 SHM 的本機運作不代表有權修改來源。單次封存成本隨主檔及 WAL 大小線性成長。合成 16 MiB 單檔三次約 52–89 ms，僅是本機抽樣。雜湊清單只驗內容和清單一致，來源世代與封存時間不是上游可信版本證明。 |

**V2-05 補測，高。** 用真實 SQLCipher 的合成資料建立版本 A（原正文）和 B（修改正文），保留同一原生 ID、房間、來源世代與最高 ID。匯入 A 後同步 B，直接重用 A 的舊清單如預期被拒絕。把 A 的原主檔位元組複製到新目錄、以 `seal` 和同世代建立新清單後，同步接受該副本，並發出新事件把正文倒回 A。因 `seal` 重新填入目前時間且不帶來源檔案識別，上界未變時無法證明其較新。應區分封存時間與可信來源版本，要求已初始化資料庫只接受可驗證往前的來源，舊副本恢復走明確流程。

## 正式套件 29／29

執行 `python3 -m unittest discover -s tests -v`，兩個 SQLCipher 環境變數都指向由官方 v4.12.0 標籤建置的 CLI 及共享函式庫。版本查詢為 4.12.0 community，共享函式庫連結 OpenSSL libcrypto.so.3。實測 0.280 秒，零略過、零失敗。加密案例中錯誤金鑰的 HMAC 診斷符合預期。

| 正式案例 | 預期及實測 |
| --- | --- |
| ambiguity_stops_room_lookup | 重名房間應拒絕，實測拒絕。 |
| author_and_thread_mutation_are_independent | 作者與討論串各應有更新，實測各有一事件。 |
| cli_snapshot_is_private_and_no_overwrite | 結果檔應私人且不可覆蓋，實測 0600、水位一致、第二次寫入失敗。 |
| copy_requires_private_directory_and_exclusive_destination | 複本應一致且獨占目的地，實測位元組一致，重複目的地及竄改拒絕。 |
| detects_replaced_capture_origin | 同世代換檔應拒絕，核准新世代則可承接，實測一致。 |
| duplicate_id_at_page_boundary_is_rejected | 重複頁界 ID 應拒絕，實測拒絕且無事件。 |
| failed_source_guard_reverts_events_and_state | 來源驗證失敗應回滾，快照和游標均一致。 |
| full_import_preserves_ids_scope_unknown_and_isolation | 應保留 ID、未知類型、引用和 Threads 並隔離他房，實測符合預期及完整性檢查。 |
| full_import_rejects_missing_native_id | 缺 ID 應拒絕，實測拒絕且未初始化。 |
| hard_process_exit_reverts_uncommitted_events | 重開後應沒有未提交變更，實測快照、游標及完整性均符合。 |
| identifier_validation_and_attachment_precision | 最大有號 64 位元 ID 應無損，實測無損且不合法輸入被拒絕。 |
| incomplete_upper_bound_rolls_back | 缺少尾頁應回滾，實測空狀態、空物件、零水位。 |
| incremental_new_and_idempotent_restart | 新增只應入庫一次，實測重開重跑零變更及零增量事件。 |
| legacy_history_kept_as_independent_evidence | 重複舊史應合一、衝突應拒絕，實測一份，快照不變。 |
| missing_record_is_retained_after_full_reconciliation | 應保留原文並標 not_observed，實測符合且重跑不重覆改動。 |
| old_snapshot_and_regressing_high_water_rejected | 舊清單與倒退上界應拒絕，實測兩者皆拒絕。 |
| one_writer_per_repository | 第二同步 writer 應鎖定失敗，實測 SQLite 拒絕。 |
| overlap_includes_floor | 重疊區底部應被納入，實測捕捉一筆異動。 |
| reconcile_finds_low_id_and_old_update | 應補載低 ID 和舊欄位，實測對帳補兩筆且無撤回事件。 |
| replaced_room_cannot_be_accepted_as_same_room | 換房後即使接受新來源世代也應拒絕，實測拒絕。 |
| repository_migrates_older_supported_schema | v1 應可升 v3 且保留世代，實測一致。 |
| repository_rejects_unrelated_database | 無關資料庫應拒絕初始化，實測拒絕。 |
| reviewed_legacy_ambiguity_never_overwrites | 多個映射應留下歧義，實測由未映射到唯一，再到歧義。 |
| room_and_schema_guards | 缺少正式欄位應拒絕，實測拒絕且未初始化。 |
| schedule_periodic_reconciliation | 到達時間門檻才應完整對帳，實測門檻前後正確且補載一次。 |
| snapshot_watermark_and_event_pagination | 跨頁接續應無缺漏，實測水位吻合、無預覽正文、異常游標被拒絕。 |
| source_generation_recovery_preserves_object_ids | 核准換來源世代應保留物件，實測原快照無變動。 |
| translations_are_versioned_and_replayed_without_body | 譯文應可冪等，錯版本應拒絕，事件不得包含譯文，實測一致。 |
| real_cipher_boundary_with_synthetic_wal | 應以 SQLCipher 讀主檔與 WAL 並保留內嵌 NUL，實測成功，錯誤金鑰同步失敗且快照一致。 |
