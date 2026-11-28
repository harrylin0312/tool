"""Sidecar storage and transactionally appended replay log."""
from contextlib import ExitStack, closing, contextmanager
from collections import defaultdict
from datetime import datetime, timezone
import unicodedata
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid

from .model import encode, fingerprint, native_id, object_id
from .witness import Witness, WitnessError

MIGRATIONS = (
    """
    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE sync_state(
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), room TEXT NOT NULL, link TEXT NOT NULL,
      source_generation TEXT NOT NULL, captured_ns INTEGER NOT NULL,
      high_water TEXT, reconciled_at REAL NOT NULL
    );
    CREATE TABLE objects(
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, native_id TEXT NOT NULL,
      data TEXT NOT NULL, version INTEGER NOT NULL, presence TEXT NOT NULL,
      UNIQUE(kind,native_id)
    );
    CREATE TABLE sources(
      id TEXT PRIMARY KEY REFERENCES objects(id), source_kind TEXT NOT NULL,
      source_generation TEXT NOT NULL, raw TEXT NOT NULL
    );
    CREATE TABLE replies(
      child TEXT PRIMARY KEY REFERENCES objects(id), target_native TEXT,
      preview TEXT, evidence TEXT NOT NULL
    );
    CREATE TABLE thread_members(
      message TEXT PRIMARY KEY REFERENCES objects(id), thread_native TEXT NOT NULL
    );
    CREATE TABLE translations(
      message TEXT NOT NULL REFERENCES objects(id), locale TEXT NOT NULL,
      original_version INTEGER NOT NULL, text TEXT NOT NULL, version INTEGER NOT NULL,
      PRIMARY KEY(message,locale,original_version)
    );
    CREATE TABLE legacy_assertions(
      source TEXT NOT NULL, legacy_id TEXT NOT NULL, object_id TEXT NOT NULL REFERENCES objects(id),
      PRIMARY KEY(source,legacy_id,object_id)
    );
    CREATE TABLE events(
      seq INTEGER PRIMARY KEY AUTOINCREMENT, schema_version INTEGER NOT NULL,
      generation TEXT NOT NULL, kind TEXT NOT NULL, object_id TEXT NOT NULL,
      version INTEGER NOT NULL, observed_at TEXT NOT NULL, change TEXT NOT NULL
    );
    """,
    """CREATE INDEX idx_thread_members_thread ON thread_members(thread_native);
       CREATE INDEX idx_events_generation_seq ON events(generation,seq);""",
    """CREATE TABLE legacy_records(
           source TEXT NOT NULL, legacy_id TEXT NOT NULL, source_kind TEXT NOT NULL,
           raw TEXT NOT NULL, PRIMARY KEY(source,legacy_id)
       );
       ALTER TABLE sync_state ADD COLUMN origin_token TEXT;""",
    """ALTER TABLE objects ADD COLUMN input_version INTEGER NOT NULL DEFAULT 1;
       UPDATE objects SET input_version=version WHERE kind='message';
       ALTER TABLE events ADD COLUMN chain TEXT;
       ALTER TABLE sync_state ADD COLUMN source_counter INTEGER;
       ALTER TABLE sync_state ADD COLUMN receipt_hash TEXT;
       INSERT INTO metadata SELECT 'repository_id',value FROM metadata WHERE key='generation';
       CREATE TABLE legacy_views(
           id TEXT PRIMARY KEY, source TEXT NOT NULL, legacy_id TEXT NOT NULL,
           data TEXT NOT NULL, version INTEGER NOT NULL, visible INTEGER NOT NULL,
           UNIQUE(source,legacy_id)
       );""",
)


class RepositoryError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_path(path):
    path = path.absolute()
    if path.is_symlink() or "com.kakao.KakaoTalkMac" in path.resolve().parts:
        raise RepositoryError("Repository must be a separate private database")
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise RepositoryError("Repository must be an independent regular file")
    return path


def database_point(db):
    meta = dict(db.execute("SELECT key,value FROM metadata"))
    generation = meta["generation"]
    tail = db.execute("SELECT * FROM events WHERE generation=? ORDER BY seq DESC LIMIT 1",
                      (generation,)).fetchone()
    state = db.execute("SELECT * FROM sync_state").fetchone()
    return {"repository": meta["repository_id"], "generation": generation,
            "seq": tail["seq"] if tail else 0, "tail": fingerprint(dict(tail)) if tail else None,
            "sync": fingerprint(dict(state) if state else None)}


def check_restore_sidecars(path):
    for suffix in ("-wal", "-shm"):
        file = path.with_name(path.name + suffix)
        if file.exists() or file.is_symlink():
            raise RepositoryError("WAL or SHM blocks repository restore")


def begin_restore_transaction(db, path):
    rollback_modes = ("delete", "truncate", "persist")
    try:
        # Persistent WAL mode may have no sidecars between connections.
        if db.execute("PRAGMA journal_mode").fetchone()[0] not in rollback_modes:
            raise RepositoryError("Restore requires rollback journal mode")
        db.execute("BEGIN EXCLUSIVE")
        check_restore_sidecars(path)
        if db.execute("PRAGMA journal_mode").fetchone()[0] not in rollback_modes:
            raise RepositoryError("Database stopped using rollback journal mode")
    except sqlite3.OperationalError as error:
        if error.sqlite_errorcode & 0xff in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise RepositoryError("Active SQLite transaction blocks repository restore") from error
        raise


def recover_rollback_journal(path, record):
    journal = path.with_name(path.name + "-journal")
    if not journal.exists() and not journal.is_symlink():
        return
    if not path.is_file():
        raise RepositoryError("Rollback journal has no repository database")
    safe_path(journal)
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True,
                                 isolation_level=None, timeout=0)) as db:
        db.row_factory = sqlite3.Row
        # SQLite owns journal recovery. No state is exposed from this connection.
        begin_restore_transaction(db, path)
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            identity = db.execute("SELECT value FROM metadata WHERE key='format'").fetchone()
            if version != len(MIGRATIONS) or not identity or identity[0] != "kakao-native-v2":
                raise RepositoryError("Journal recovery requires a recognized repository")
            point = database_point(db)
            if point not in (record["committed"], record["pending"]):
                raise WitnessError("Recovered repository does not match either witnessed endpoint")
            # A cold journal may survive read-only opening. A same-value header transaction
            # lets SQLite clean it up through ordinary commit without changing the event state.
            db.execute(f"PRAGMA user_version={version}")
            if database_point(db) != point:
                raise WitnessError("Recovery changed the witnessed event state")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    if journal.exists():
        raise RepositoryError("SQLite did not finish rollback journal recovery")
    return point


@contextmanager
def lock_restore_database(path, *, allow_missing=False, recovered_point=None):
    """Hold an exclusive rollback-mode transaction until restore confirmation."""
    check_restore_sidecars(path)
    journal = path.with_name(path.name + "-journal")
    if journal.exists() or journal.is_symlink():
        raise RepositoryError("Rollback journal appeared during repository restore")
    if not path.is_file():
        if not allow_missing:
            raise RepositoryError("Missing database during restore")
        yield
        return
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True,
                                 isolation_level=None, timeout=0)) as db:
        db.row_factory = sqlite3.Row
        begin_restore_transaction(db, path)
        if journal.exists() or journal.is_symlink():
            raise RepositoryError("Rollback journal appeared during repository restore")
        if recovered_point is not None and database_point(db) != recovered_point:
            raise WitnessError("Repository changed after rollback journal recovery")
        yield


class Repository:
    def __init__(self, path, initialize=False, *, witness=None, adopt=False):
        self.witness_record = None
        self._writing = False
        self.path = safe_path(Path(path))
        self.witness = Witness(witness or self.path.with_name(self.path.name + ".witness"))
        if self.witness.path.resolve() == self.path.resolve():
            raise RepositoryError("Witness and database paths must differ")
        with self.witness.locked():
            existing = self.witness.read()
            if initialize and not self.path.exists() and existing is None:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            if not self.path.is_file():
                raise RepositoryError("Initialize the sidecar repository first")
            self.identity = self._identity()
            self.db = sqlite3.connect(self.path, isolation_level=None, timeout=0)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA synchronous=FULL")
            try:
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if existing is None:
                    if not ((initialize and not version) or (adopt and 0 < version < 4)):
                        raise WitnessError("Missing external witness; explicit v3 adoption or trusted restore required")
                else:
                    if version < 4 and not self.db.execute(
                        "SELECT 1 FROM metadata WHERE key='repository_id'").fetchone():
                        raise WitnessError("Repository was replaced with an unrecognized earlier backup")
                    self.witness.verify(self._point())
                self._migrate(initialize)
                if existing is None:
                    if adopt:
                        self.db.execute("UPDATE metadata SET value=? WHERE key='generation'", (uuid.uuid4().hex,))
                    self.witness.write({"format": 1, "committed": self._point(), "pending": None})
                self.generation = self._meta("generation")
            except BaseException:
                self.db.close()
                raise

        if self._meta("legacy_projection_policy") != "2":
            try:
                with self.transaction(write=True):
                    self.refresh_legacy()
                    self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('legacy_projection_policy','2')")
            except BaseException:
                self.db.close()
                raise

    def _identity(self):
        st = self.path.stat()
        return st.st_dev, st.st_ino

    def _meta(self, name):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (name,)).fetchone()
        return row[0] if row else None

    def _point(self):
        return database_point(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.db.close()

    @contextmanager
    def _transaction(self, *, write=False):
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    @contextmanager
    def transaction(self, *, write=False):
        with self.witness.locked():
            if self._identity() != self.identity:
                raise WitnessError("Repository file changed; reopen it")
            record = self.witness.verify(self._point())
            point = record["committed"]
            with self._transaction(write=write):
                self.witness_record = record
                self._writing = write
                try:
                    yield
                    proposed = self._point() if write else point
                    if proposed != point:
                        record["pending"] = proposed
                        self.witness.write(record)
                finally:
                    self.witness_record = None
                    self._writing = False
            if proposed != point:
                self.witness.verify(proposed)

    @contextmanager
    def _coordinated_read(self):
        if self.witness_record is not None:
            yield
        else:
            with self.transaction():
                yield

    def _require_write(self):
        if not self._writing:
            raise RepositoryError("A coordinated write transaction is required")

    def _migrate(self, initialize):
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RepositoryError("Unsupported repository schema")
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if not version and (not initialize or tables):
            raise RepositoryError("Refusing to initialize an existing unrecognized database")
        if version and "metadata" not in tables:
            raise RepositoryError("Unrecognized repository schema")
        with self._transaction(write=True) if version < len(MIGRATIONS) else self._transaction():
            if version and tuple(self.db.execute("SELECT value FROM metadata WHERE key='format'").fetchone() or ()) != ("kakao-native-v2",):
                raise RepositoryError("Unrecognized repository format")
            for migration in MIGRATIONS[version:]:
                for statement in migration.split(";"):
                    if statement.strip():
                        self.db.execute(statement)
                version += 1
                self.db.execute(f"PRAGMA user_version={version}")
            if not tables:
                self.db.executemany("INSERT INTO metadata VALUES (?,?)",
                                    [("format", "kakao-native-v2"), ("generation", uuid.uuid4().hex),
                                     ("repository_id", uuid.uuid4().hex)])
        self.generation = self.db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0]

    def state(self):
        with self._coordinated_read():
            state = self.db.execute("SELECT * FROM sync_state").fetchone()
            return dict(state) if state else None

    def save_state(self, room, link, source_generation, captured_ns, high_water, reconciled, origin_token,
                   source_counter=None, receipt_hash=None):
        self._require_write()
        self.db.execute("""INSERT INTO sync_state VALUES (1,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(singleton) DO UPDATE SET source_generation=excluded.source_generation,
            captured_ns=excluded.captured_ns, high_water=excluded.high_water,
            reconciled_at=excluded.reconciled_at,origin_token=excluded.origin_token,
            source_counter=excluded.source_counter,receipt_hash=excluded.receipt_hash""",
            (room, link, source_generation, captured_ns, high_water, reconciled, origin_token,
             source_counter, receipt_hash))

    def emit(self, kind, uid, version, change, *, state_proof=None):
        self._require_write()
        timestamp = now()
        payload = encode(change)
        tail = self.db.execute("SELECT seq,chain FROM events WHERE generation=? ORDER BY seq DESC LIMIT 1",
                               (self.generation,)).fetchone()
        chain = fingerprint([tuple(tail) if tail else None, kind, uid, version, timestamp, payload, state_proof])
        self.db.execute("""INSERT INTO events(schema_version,generation,kind,object_id,version,
            observed_at,change,chain) VALUES (2,?,?,?,?,?,?,?)""",
            (self.generation, kind, uid, version, timestamp, payload, chain))

    def put(self, room, kind, row, source_generation, historical):
        self._require_write()
        nid = native_id(row["id"])
        uid = object_id(room, kind, nid)
        # Preserve full source evidence. The normalized projection separates relations.
        raw = encode(row)
        view = {k: v for k, v in row.items()
                if k not in {"attachment", "reply_target", "reply_preview", "reply_evidence", "thread"}}
        if kind == "message":
            view["visibility_semantics"] = "unverified"
        data = encode(view)
        previous = self.db.execute("""SELECT o.data,o.version,o.input_version,o.presence,s.raw,s.source_generation
            FROM objects o JOIN sources s ON s.id=o.id WHERE o.id=?""", (uid,)).fetchone()
        if previous and previous["raw"] == raw and previous["presence"] == "observed":
            if previous["source_generation"] != source_generation:
                self.db.execute("UPDATE sources SET source_generation=? WHERE id=?", (source_generation, uid))
            return False
        version = previous["version"] + 1 if previous else 1
        prior = json.loads(previous["raw"]) if previous else {}
        input_version = previous["input_version"] if previous else 1
        if previous and kind == "message" and prior.get("body") != row.get("body"):
            input_version += 1
        self.db.execute("""INSERT INTO objects(id,kind,native_id,data,version,presence,input_version)
            VALUES (?,?,?,?,?,'observed',?) ON CONFLICT(id) DO UPDATE SET
            data=excluded.data,version=excluded.version,presence=excluded.presence,input_version=excluded.input_version""",
            (uid, kind, nid, data, version, input_version))
        self.db.execute("""INSERT INTO sources VALUES (?,'kakao-native',?,?)
            ON CONFLICT(id) DO UPDATE SET source_generation=excluded.source_generation,raw=excluded.raw""",
            (uid, source_generation, raw))
        if kind == "message":
            self.db.execute("""INSERT INTO replies VALUES (?,?,?,?)
                ON CONFLICT(child) DO UPDATE SET target_native=excluded.target_native,
                preview=excluded.preview,evidence=excluded.evidence""",
                (uid, row.get("reply_target"), row.get("reply_preview"), row.get("reply_evidence", "absent")))
            self.db.execute("DELETE FROM thread_members WHERE message=?", (uid,))
            if row.get("thread"):
                self.db.execute("INSERT INTO thread_members VALUES (?,?)", (uid, row["thread"]))
        verb = "created" if kind == "message" and previous is None else "updated"
        names = sorted(k for k in set(prior) | set(row) if prior.get(k) != row.get(k))
        self.emit(f"{kind}.{verb}", uid, version, {"historical": historical, "fields": names,
                                                   "presence": "observed"}, state_proof=fingerprint(row))
        return True

    def note_absent(self, kind, seen):
        self._require_write()
        rows = self.db.execute("SELECT id,native_id,version FROM objects WHERE kind=? AND presence='observed'", (kind,))
        count = 0
        for row in rows.fetchall():
            if row["native_id"] not in seen:
                version = row["version"] + 1
                self.db.execute("UPDATE objects SET presence='not_observed',version=? WHERE id=?", (version, row["id"]))
                self.emit(f"{kind}.updated", row["id"], version, {"presence": "not_observed"})
                count += 1
        return count

    def preserve_legacy(self, source, legacy_id, source_kind, payload):
        if source_kind not in {"app-export", "ui-derived", "legacy-html", "unknown"}:
            raise RepositoryError("Unknown legacy source kind")
        raw = encode(payload)
        with self.transaction(write=True):
            prior = self.db.execute("SELECT source_kind,raw FROM legacy_records WHERE source=? AND legacy_id=?",
                                    (source, legacy_id)).fetchone()
            if prior and tuple(prior) != (source_kind, raw):
                raise RepositoryError("Legacy observation conflicts; retain as a different source version")
            if not prior:
                self.db.execute("INSERT INTO legacy_records VALUES (?,?,?,?)",
                                (source, legacy_id, source_kind, raw))

    def map_legacy(self, source, legacy_id, uid):
        # Caller must supply reviewed candidates; multiple assertions remain ambiguous.
        with self.transaction(write=True):
            kind = self.db.execute("SELECT kind FROM objects WHERE id=?", (uid,)).fetchone()
            if not kind or kind[0] != "message":
                raise RepositoryError("Legacy mapping needs an existing message")
            added = self.db.execute("INSERT OR IGNORE INTO legacy_assertions VALUES (?,?,?)",
                                    (source, legacy_id, uid)).rowcount
            if added:
                self.emit("legacy.mapping_updated", "legacy_" + fingerprint([source, legacy_id]),
                          self.db.execute("SELECT count(*) FROM legacy_assertions WHERE source=? AND legacy_id=?",
                                          (source, legacy_id)).fetchone()[0], {}, state_proof=fingerprint([uid]))
                self.refresh_legacy()

    def legacy_mapping(self, source, legacy_id):
        with self._coordinated_read():
            rows = self.db.execute("SELECT object_id FROM legacy_assertions WHERE source=? AND legacy_id=?",
                                   (source, legacy_id)).fetchall()
            return ("unique", rows[0][0]) if len(rows) == 1 else ("ambiguous" if rows else "unmapped", None)

    def translate(self, uid, locale, source_version, text):
        with self.transaction(write=True):
            row = self.db.execute("SELECT input_version FROM objects WHERE id=? AND kind='message'", (uid,)).fetchone()
            if not row or row["input_version"] != source_version:
                raise RepositoryError("Translation input message version is stale")
            args = (uid, locale, source_version)
            prior = self.db.execute("""SELECT text,version FROM translations
                WHERE message=? AND locale=? AND original_version=?""", args).fetchone()
            if prior and prior["text"] == text:
                return False
            version = prior["version"] + 1 if prior else 1
            self.db.execute("""INSERT INTO translations VALUES (?,?,?,?,?)
                ON CONFLICT(message,locale,original_version) DO UPDATE SET
                text=excluded.text,version=excluded.version""", (*args, text, version))
            self.emit("translation.completed", "translation_" + fingerprint(args), version,
                      {"message_id": uid, "locale": locale, "input_version": source_version},
                      state_proof=fingerprint([text]))
            return True

    def watermark(self):
        with self._coordinated_read():
            return self.db.execute("SELECT coalesce(max(seq),0) FROM events WHERE generation=?", (self.generation,)).fetchone()[0]

    def replay(self, generation, after, limit):
        if generation != self.generation:
            raise RepositoryError("Event generation mismatch, request a new snapshot")
        with self.transaction():
            if after > self.watermark():
                raise RepositoryError("Event cursor is ahead of this repository")
            return [{**dict(row), "change": json.loads(row["change"])} for row in self.db.execute(
                "SELECT seq,schema_version,generation,kind,object_id,version,observed_at,change FROM events WHERE generation=? AND seq>? ORDER BY seq LIMIT ?",
                (generation, after, limit))]

    def _projection(self):
        result = {"generation": self.generation, "event_schema_version": 2,
                  "event_seq": self.watermark()}
        for table in ("objects", "replies", "thread_members"):
            result[table] = [dict(row) for row in self.db.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
        for row in result["objects"]:
            row["data"] = json.loads(row["data"])
        result["translations"] = [dict(row) for row in self.db.execute("""
            SELECT t.* FROM translations t JOIN objects o ON o.id=t.message
            AND o.input_version=t.original_version ORDER BY t.message,t.locale""")]
        result["legacy_assertions"] = [
            {"source_ref": fingerprint([row[0]]), "legacy_id": row[1], "object_id": row[2]}
            for row in self.db.execute("SELECT source,legacy_id,object_id FROM legacy_assertions ORDER BY 1,2,3")
        ]
        result["legacy"] = [
            {**dict(row), "data": json.loads(row["data"])}
            for row in self.db.execute(
                "SELECT id,data,version FROM legacy_views WHERE visible=1 ORDER BY id")
        ]
        return result

    def snapshot(self):
        with self.transaction():
            return self._projection()

    def changes(self, generation, after):
        """Materialize an immutable batch at one read watermark."""
        if type(after) is not int or after < 0:
            raise RepositoryError("Invalid change cursor")
        with self.transaction():
            end = self.watermark()
            reason = None
            if generation != self.generation:
                reason = "generation_mismatch"
            elif after > end or (after and not self.db.execute(
                    "SELECT 1 FROM events WHERE generation=? AND seq=?", (generation, after)).fetchone()):
                reason = "history_unavailable"
            selected = None
            replace_legacy = bool(reason)
            if reason is None:
                selected = set()
                for row in self.db.execute("""SELECT kind,object_id,change FROM events
                    WHERE generation=? AND seq>? AND seq<=? ORDER BY seq""", (generation, after, end)):
                    if row["kind"].startswith("legacy."):
                        replace_legacy = True
                    elif row["kind"] == "translation.completed":
                        selected.add(json.loads(row["change"])["message_id"])
                    else:
                        selected.add(row["object_id"])
            view = self._projection() if selected != set() or replace_legacy else {
                name: [] for name in ("objects", "replies", "thread_members", "translations")
            }
            bundles = {
                row["id"]: {"object": row, "reply": None, "thread_member": None, "translations": []}
                for row in view["objects"] if selected is None or row["id"] in selected
            }
            for field, table, foreign in (("reply", "replies", "child"),
                                           ("thread_member", "thread_members", "message"),
                                           ("translations", "translations", "message")):
                for row in view[table]:
                    uid = row[foreign]
                    if uid in bundles:
                        if field == "translations":
                            bundles[uid][field].append(row)
                        else:
                            bundles[uid][field] = row
            records = [{"section": "object", "value": bundle} for bundle in bundles.values()]
            if replace_legacy:
                records.extend({"section": "legacy", "value": row} for row in view["legacy"])
                records.extend({"section": "mapping", "value": row} for row in view["legacy_assertions"])
            batch = {"schema_version": 2, "generation": self.generation,
                     "requested_generation": generation, "start": after, "end": end,
                     "mode": "snapshot" if reason else "delta", "reset_reason": reason,
                     "replace_legacy_and_mappings": replace_legacy, "records": records}
            batch["batch_id"] = fingerprint(batch)
            return batch

    def publish_legacy(self, source, legacy_id, *, body, author, timestamp, precision,
                       confidence, reviewed):
        """Publish reviewed, field-whitelisted historical data separately from evidence."""
        if reviewed is not True or confidence != "reviewed":
            raise RepositoryError("Legacy publication requires independent review")
        if not isinstance(body, str) or not body or not isinstance(author, str):
            raise RepositoryError("Invalid legacy display fields")
        if precision not in ("second", "minute", "unknown"):
            raise RepositoryError("Invalid legacy time precision")
        parsed = None
        if precision != "unknown":
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None or parsed.microsecond or (precision == "minute" and parsed.second):
                raise RepositoryError("Legacy time requires a zone and matching precision")
            timestamp = parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        elif timestamp is not None:
            raise RepositoryError("Unknown time precision requires null timestamp")
        with self.transaction(write=True):
            row = self.db.execute("SELECT source_kind FROM legacy_records WHERE source=? AND legacy_id=?",
                                  (source, legacy_id)).fetchone()
            if not row:
                raise RepositoryError("Legacy evidence must be preserved first")
            uid = "history_" + fingerprint([source, legacy_id])
            data = {"body": body, "author": author, "timestamp": timestamp, "precision": precision,
                    "source_kind": row[0], "source_ref": fingerprint([source]),
                    "mapping_state": "unmapped", "confidence": confidence}
            current = self.db.execute("SELECT data,version,visible FROM legacy_views WHERE id=?", (uid,)).fetchone()
            if current:
                data["mapping_state"] = json.loads(current["data"])["mapping_state"]
            encoded = encode(data)
            if current and current["data"] == encoded:
                return uid
            # Start as hidden and decide visibility against native and other historical candidates.
            self.db.execute("""INSERT INTO legacy_views VALUES (?,?,?,?,?,0)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data""",
                (uid, source, legacy_id, encoded, 0))
            self.refresh_legacy(force={uid})
            return uid

    def refresh_legacy(self, force=frozenset()):
        self._require_write()
        rows = self.db.execute("SELECT * FROM legacy_views ORDER BY visible DESC,id").fetchall()
        if not rows:
            return set()

        def match_key(body, author):
            return " ".join(unicodedata.normalize("NFC", body or "").split()), " ".join(
                unicodedata.normalize("NFC", author or "").split())

        def present(candidate, other):
            # Same normalized text and author plus an intersecting time window is ambiguous.
            # Unknown times conservatively overlap any time for that author+text.
            if candidate[0] is None or other[0] is None:
                return True
            return candidate[0] < other[1] and other[0] < candidate[1]

        def interval(timestamp, precision):
            if timestamp is None:
                return None, None
            start = datetime.fromisoformat(timestamp).timestamp()
            return start, start + (60 if precision == "minute" else 1)

        authors = {r[0]: json.loads(r[1]).get("name") for r in self.db.execute(
            "SELECT native_id,data FROM objects WHERE kind='author'")}
        native = defaultdict(list)
        for r in self.db.execute("SELECT id,data FROM objects WHERE kind='message'"):
            m = json.loads(r["data"])
            key = match_key(m.get("body"), authors.get(m.get("author")))
            t = m.get("sent_at")
            native[key].append((r["id"], (t, t + 1) if t is not None else (None, None)))
        claims = defaultdict(set)
        explicit = defaultdict(set)
        reviewed = {r["id"]: r for r in rows}
        for r in self.db.execute("""SELECT v.id,a.object_id FROM legacy_views v JOIN legacy_assertions a
                ON a.source=v.source AND a.legacy_id=v.legacy_id"""):
            claims[r["object_id"]].add(r["id"])
            explicit[r["id"]].add(r["object_id"])
        confirmed = {uid: next(iter(ids)) for uid, ids in explicit.items()
                     if len(ids) == 1 and len(claims[next(iter(ids))]) == 1}
        groups = defaultdict(list)
        candidates = defaultdict(set)
        known_time = {}
        for row in rows:
            uid = row["id"]
            data = json.loads(row["data"])
            key = match_key(data["body"], data["author"])
            window = interval(data["timestamp"], data["precision"])
            known_time[uid] = window[0] is not None
            groups[key].append((uid, window))
            for target, target_window in native[key]:
                if present(window, target_window):
                    known_time[target] = target_window[0] is not None
                    candidates[uid].add(target)
                    candidates[target].add(uid)
        for group in groups.values():
            for i, (uid, window) in enumerate(group):
                for other, other_window in group[i + 1:]:
                    if reviewed[uid]["source"] != reviewed[other]["source"] and present(window, other_window):
                        candidates[uid].add(other)
                        candidates[other].add(uid)

        state = {uid: "unmapped" for uid in reviewed}
        for uid in reviewed:
            if uid in confirmed:
                state[uid] = "matched"
                continue
            options = candidates[uid]
            if uid in explicit:
                state[uid] = "ambiguous"
            elif len(options) == 1:
                other = next(iter(options))
                if (candidates[other] == {uid} and other not in explicit and other not in claims
                        and known_time[uid] and known_time[other]):
                    # The existing visible row wins a unique legacy-only pair.
                    if other not in reviewed or (not reviewed[other]["visible"], other) < (not reviewed[uid]["visible"], uid):
                        state[uid] = "matched"
                else:
                    state[uid] = "ambiguous"
            elif options:
                state[uid] = "ambiguous"

        changed = set()
        for row in rows:
            uid = row["id"]
            data = json.loads(row["data"])
            previous = data["mapping_state"]
            data["mapping_state"] = state[uid]
            visible = state[uid] != "matched"
            if visible != bool(row["visible"]) or (visible and (uid in force or previous != state[uid])):
                version = row["version"] + 1
                self.db.execute("UPDATE legacy_views SET version=?,visible=?,data=? WHERE id=?",
                                (version, int(visible), encode(data), uid))
                self.emit("legacy.projection_updated", uid, version, {"visible": visible},
                          state_proof=fingerprint(data))
                changed.add(uid)
            elif previous != state[uid]:
                self.db.execute("UPDATE legacy_views SET data=? WHERE id=?", (encode(data), uid))
        return changed

    def statistics(self):
        with self.transaction():
            return {"generation": self.generation, "event_seq": self.watermark(),
                    "initialized": self.state() is not None,
                    "objects": {r["kind"]: r["n"] for r in self.db.execute(
                        "SELECT kind,count(*) n FROM objects GROUP BY kind")},
                    "not_observed": self.db.execute(
                        "SELECT count(*) FROM objects WHERE presence='not_observed'").fetchone()[0],
                    "replies": self.db.execute("SELECT count(*) FROM replies WHERE target_native IS NOT NULL").fetchone()[0],
                    "thread_members": self.db.execute("SELECT count(*) FROM thread_members").fetchone()[0]}

    def verify(self):
        with self.transaction():
            return (self.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    and not self.db.execute("PRAGMA foreign_key_check").fetchall())

    def backup(self, destination):
        destination = safe_path(destination)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with self.transaction():
                other = sqlite3.connect(destination)
                try:
                    self.db.backup(other)
                finally:
                    other.close()
        except BaseException:
            destination.unlink()
            raise

    @classmethod
    def restore(cls, path, backup, *, witness=None):
        """Replace the sidecar from an authenticated repository lineage and rotate generation."""
        path, backup = safe_path(path), safe_path(backup)
        control = Witness(witness or path.with_name(path.name + ".witness"))
        if path.resolve() == backup.resolve() or control.path.resolve() in (path.resolve(), backup.resolve()):
            raise RepositoryError("Restore paths must be distinct")
        with control.locked():
            record = control.read()
            if not record or not backup.is_file():
                raise RepositoryError("Restore requires the existing witness and a backup")
            check_restore_sidecars(path)
            with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
                candidate = Path(tmp) / "restored"
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                source = sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)
                target = sqlite3.connect(candidate)
                try:
                    source.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RepositoryError("Backup failed integrity check")
                    if target.execute("PRAGMA foreign_key_check").fetchone():
                        raise RepositoryError("Backup failed foreign key check")
                    if target.execute("PRAGMA user_version").fetchone()[0] != len(MIGRATIONS):
                        raise RepositoryError("Backup schema is incompatible")
                    identity = target.execute("SELECT value FROM metadata WHERE key='repository_id'").fetchone()
                    if not identity or identity[0] != record["committed"]["repository"]:
                        raise RepositoryError("Backup belongs to another repository")
                    generation = uuid.uuid4().hex
                    target.execute("UPDATE metadata SET value=? WHERE key='generation'", (generation,))
                    target.commit()
                    target.row_factory = sqlite3.Row
                    state = target.execute("SELECT * FROM sync_state").fetchone()
                    point = {"repository": identity[0], "generation": generation, "seq": 0,
                             "tail": None, "sync": fingerprint(dict(state) if state else None)}
                finally:
                    source.close()
                    target.close()
                # Do not open/close a separate fd on either inode after taking
                # SQLite's POSIX locks. Flush the candidate before locking it.
                with candidate.open("rb") as handle:
                    os.fsync(handle.fileno())
                recovered_point = recover_rollback_journal(path, record)
                with ExitStack() as locks:
                    locks.enter_context(lock_restore_database(
                        path, allow_missing=recovered_point is None, recovered_point=recovered_point
                    ))
                    locks.enter_context(lock_restore_database(candidate))
                    record["pending"] = point
                    control.write(record)
                    os.replace(candidate, path)
                    directory = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                    control.verify(point)
        return generation
