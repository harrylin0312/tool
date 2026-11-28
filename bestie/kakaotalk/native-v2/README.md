# KakaoTalk Reader V2 本機核心

從 `bestie/kakaotalk/native-v2` 執行。需 Python 3.11+ 及已核准的 SQLCipher 4.12.0 動態庫。標準函式庫處理旁路 SQLite 和一致性變更批次。資料庫、擷取檔案、備份和投影須留在 Git 之外的私人目錄。SQLCipher 以相容模式 3 開啟複本。

## 初始化及來源

```sh
python3 -m core init --repo "$REPO" --witness "$WITNESS"
python3 -m core bind-source --repo "$REPO" --witness "$WITNESS" --source-db "$KNOWN_SOURCE" --source-generation local-1
python3 -m core capture --repo "$REPO" --witness "$WITNESS" --source-db "$KNOWN_SOURCE" --source-generation local-1 --snapshot "$FIRST_COPY"
python3 -m core import --repo "$REPO" --witness "$WITNESS" --snapshot "$FIRST_COPY" --room "$ROOM_TITLE" --sqlcipher "$SQLCIPHER_LIBRARY"
```

日常擷取從首次定位確認的原始檔開始。import、sync、reconcile 以私人程序管線從 stdin 取得一行解鎖材料。每次 capture 用新的目錄，以相同綁定取得收據，再執行 sync。收據記錄在見證檔且只承認最新一次擷取，失敗擷取後可重試出新的收據。資料夾可用 0700 保護。

封存既有複本的 seal 不簽發收據。這類外部副本可由操作者明確選擇作空庫歷史匯入。已有同步狀態時，外部副本只可使用不同來源世代，經 reconcile 加 `--accept-source-generation --recover-external` 完整復原。只有在人工確認確實需要舊資料復原時使用。真實來源換檔，須驗證來源後 bind-source 加 `--replace-binding` 和新來源世代，重新擷取再以 reconcile 加 `--accept-source-generation`。同房間及原有映射檢查仍會生效。

若來源在 capture 期間改變，擷取會安全停止，可稍後重試。複製與封存都只是穩定副本證據，KakaoTalk 尚無可直接核對的全域版本保證。旁路中不存在可認證的舊副本時不可重造同一來源世代。正常程式仍接受已綁定檔案中正文修改。

## 狀態、事件及備份

除了 page，下面需要 `--repo "$REPO" --witness "$WITNESS"`。未指定 witness 時，用和旁路資料庫相鄰的 `.witness`，正式測試應放到獨立路徑，並在後續命令沿用。常見呼叫如下。

```sh
python3 -m core status --repo "$REPO" --witness "$WITNESS"
python3 -m core stats --repo "$REPO" --witness "$WITNESS"
python3 -m core verify --repo "$REPO" --witness "$WITNESS"
python3 -m core changes --repo "$REPO" --witness "$WITNESS" --generation bootstrap --after 0 --output "$BATCH"
python3 -m core page --batch "$BATCH" --offset 0 --limit 100 --output "$PAGE"
python3 -m core backup --repo "$REPO" --witness "$WITNESS" --output "$BACKUP"
python3 -m core restore --repo "$REPO" --witness "$WITNESS" --backup "$BACKUP"
```

status 提供健康水位及來源信任分類。snapshot 可輸出原子私有投影，events 可檢視失效提示，changes/page 用在可一致套用的版本投影。請見 [事件協定](../docs/architecture/EVENT-PROTOCOL.md)。資料檔為 0600，CLI 僅回報摘要。歷史顯示層可使用 Repository.preserve_legacy 與 publish_legacy，來源識別應用無私人資料的本機代號。

備份只包含旁路 SQLite。見證檔是私人可信狀態，包含擷取簽章材料，應留在獨立持久位置。保留目前見證檔。若檔案與見證不符，停止操作並確認備份及見證狀態。見證遺失時，無法自動從舊檔恢復同一世代。

正式元件須透過 Repository 或受控介面存取旁路資料庫。開始還原前，停止接收新工作、等待既有交易結束並關閉受控連線，接著執行 `restore`。還原持有外部見證鎖，新 Repository 操作會收到忙碌錯誤。還原成功後重新開啟 Repository，再恢復服務。既有 Repository 控制代碼遇到換檔會拒絕後續操作。舊世代的客戶端須取得完整投影。

還原前若有冷或熱 rollback journal，由 SQLite 恢復並查核見證端點。正式換檔前一律取得 rollback 模式的 SQLite 獨占交易，並鎖住候選檔，直到換檔及見證確認完成才關閉連線。若 SQLite 讀寫交易正在持鎖，或資料庫為 WAL 模式、存在 WAL／SHM，還原會拒絕。請等待使用者關閉連線，勿手動移除 journal。SQLite 鎖保護目前檔案 inode 上的交易。未持鎖的外部閒置連線無法可靠偵測，SQLite 鎖也無法阻止外部直接換檔。直接開啟旁路 SQLite 的外部連線不受支援。

已知的 V1–V3 P2 旁路資料庫須先做私人備份，再用 `adopt --repo "$REPO" --witness "$WITNESS"`。adopt 保留 ID、映射和譯文並旋轉世代。舊客戶端需重新取得完整投影。既有來源憑證保留在本機，P2.1 需新增一次 bind-source 才能日常擷取。

## 測試

```sh
python3 -m unittest discover -s tests -v
```

設定 `KAKAO_TEST_SQLCIPHER` 和 `KAKAO_TEST_SQLCIPHER_CLI` 指向已核准的動態庫和 CLI，可執行兩項合成加密測試。其他測試使用隔離 SQLite。[P2.1 修正報告](../docs/research/P2-QA-REMEDIATION.md)

[P2.2 最小缺陷修正](../docs/research/P2.2-REMEDIATION.md)

[P2.3 還原並行控制修正](../docs/research/P2.3-REMEDIATION.md)
