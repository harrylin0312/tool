# V2 本機事件協定

P2 schema version 為 1。每筆包含 seq、schema_version、generation、kind、object_id、version、observed_at、change。seq 是本機單調遞增的 SQLite 整數。跨平台客戶端若不能精確處理整數，後續傳輸層須以字串傳遞。generation 是旁路資料集的 UUID，來源資料庫世代是另一個值。經明確核准的同房間來源替換可保留本機世代與書籤。重新初始化資料集會生成新世代。

- `message.created`、`message.updated` 保留觀察到的版本及改動欄位。首次匯入及落在既有游標內的補載標示 historical。
- `author.updated`、`thread.updated` 包括首次觀察和後續變動。
- `translation.completed` 附語系與原文版本，新譯文以自己的穩定 ID 及版本記錄。
- `legacy.mapping_updated` 提示介面刷新舊 ID 映射。
- 未確認撤回時，保留來源類型及欄位變動，待語義驗證。事件內容只有物件 ID、版本、欄位名、觀察狀態等資訊，原文或引文從授權的私有資料投影查取。

CLI snapshot 在同一筆讀取交易取出投影與 event_seq。events 需要相同 generation，按 seq 查指定游標之後的事件。世代不同或游標領先時回報錯誤。事件保留策略、跨設備身份驗證、敏感內容投影與網路傳輸由後續階段定案。因本輪未清除事件，當前未實作保留期限截斷。

歷史不可原地覆寫以偽造重播。同步在一筆本機交易提交物件、事件與游標。失敗時一起回滾；重播相同觀察不新增事件。未來公開給客戶端的快照由此私有投影再產生，完整 CLI 測試快照只供本地驗收。
