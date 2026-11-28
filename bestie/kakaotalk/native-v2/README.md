# KakaoTalk Reader V2 本機核心

本目錄可獨立執行，使用 Python 3.11+ 和既經批准建置的 SQLCipher 4.12.0 動態函式庫。本機 SHA-256 封存、SQLite 與同步均使用標準函式庫。SQLCipher 以相容模式 3 開啟隔離副本。日常操作從已確認的本機來源路徑開始，定位及金鑰取得留在核准的本機流程。

Python 3.11、3.12、3.13、3.14 可執行；候選驗收使用 3.14。將已核准建置的 SQLCipher artifact 留在私人目錄，使用絕對路徑指定 `--sqlcipher`。旁路資料庫使用這個 Python 內建的 SQLite。從任意位置啟動時，把工作目錄設為本目錄即可，無需 pip 或全域安裝。

## CLI

以下指令從 `bestie/kakaotalk/native-v2` 執行。目的地使用權限 700 的私人目錄，資料庫、封存副本和測試快照均放在 Git 儲存庫外。`--source-generation` 是自選不含隱私的穩定代號，來源檔案替換須新代號。每次 capture 用新的 snapshot 目錄。

```sh
python3 -m core init --repo /private/sidecar/repo.sqlite
python3 -m core capture --source-db /private/known-source --snapshot /private/sidecar/snapshot-1 --source-generation local-1
python3 -m core import --repo /private/sidecar/repo.sqlite --snapshot /private/sidecar/snapshot-1 --room "$ROOM_TITLE" --sqlcipher "$SQLCIPHER_LIBRARY"
python3 -m core status --repo /private/sidecar/repo.sqlite
python3 -m core stats --repo /private/sidecar/repo.sqlite
python3 -m core snapshot --repo /private/sidecar/repo.sqlite --output /private/sidecar/test-export.json
python3 -m core events --repo /private/sidecar/repo.sqlite --generation "$LOCAL_GENERATION" --after 0
python3 -m core verify --repo /private/sidecar/repo.sqlite
```

import、sync、reconcile 透過 stdin 接收一行來源金鑰。使用私人程序管線，避免 shell history 或可見終端輸入。後續用 capture 產生新封存副本，以相同選項改用 sync。`--overlap` 和 `--reconcile-interval` 預設 100 列和 3600 秒，可調整。reconcile 立即完整對帳。來源世代變更時，以 reconcile 加 `--accept-source-generation` 明確恢復至已確認的同一房間。截斷水位或讀錯房間會停止。需要把已知一致的外部副本交給 CLI 時，先將主檔及同時段 WAL 放在私人目錄，再以 seal 建清單；seal 只驗內容未再改動，無法證明來源本身一致。若來源在 capture 時一直寫入，待穩定後重試或使用離線一致性副本。

## 自動化測試

```sh
python3 -m unittest discover -s tests -v
```

另設 `KAKAO_TEST_SQLCIPHER` 及 `KAKAO_TEST_SQLCIPHER_CLI` 指向已核准的 library 和 CLI，可執行合成加密 WAL 測試。一般測試皆建立臨時 SQLite，不觸碰正式資料。[驗收報告](../docs/research/P2-IMPLEMENTATION-REPORT.md)
