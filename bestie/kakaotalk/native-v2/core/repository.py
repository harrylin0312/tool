"""Sidecar storage and transactionally appended replay log."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .model import encode, fingerprint, native_id, object_id

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


class Repository:
    def __init__(self, path, initialize=False):
        path = safe_path(Path(path))
        if initialize and not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        if not path.is_file():
            raise RepositoryError("Initialize the sidecar repository first")
        self.db = sqlite3.connect(path, isolation_level=None, timeout=0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        try:
            self._migrate(initialize)
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.db.close()

    @contextmanager
    def transaction(self, *, write=False):
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _migrate(self, initialize):
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RepositoryError("Unsupported repository schema")
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if not version and (not initialize or tables):
            raise RepositoryError("Refusing to initialize an existing unrecognized database")
        if version and "metadata" not in tables:
            raise RepositoryError("Unrecognized repository schema")
        with self.transaction(write=True) if version < len(MIGRATIONS) else self.transaction():
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
                                    [("format", "kakao-native-v2"), ("generation", uuid.uuid4().hex)])
        self.generation = self.db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0]

    def state(self):
        state = self.db.execute("SELECT * FROM sync_state").fetchone()
        return dict(state) if state else None

    def save_state(self, room, link, source_generation, captured_ns, high_water, reconciled, origin_token):
        self.db.execute("""INSERT INTO sync_state VALUES (1,?,?,?,?,?,?,?)
            ON CONFLICT(singleton) DO UPDATE SET source_generation=excluded.source_generation,
            captured_ns=excluded.captured_ns, high_water=excluded.high_water,
            reconciled_at=excluded.reconciled_at,origin_token=excluded.origin_token""",
            (room, link, source_generation, captured_ns, high_water, reconciled, origin_token))

    def emit(self, kind, uid, version, change):
        self.db.execute("""INSERT INTO events(schema_version,generation,kind,object_id,version,
            observed_at,change) VALUES (1,?,?,?,?,?,?)""",
            (self.generation, kind, uid, version, now(), encode(change)))

    def put(self, room, kind, row, source_generation, historical):
        nid = native_id(row["id"])
        uid = object_id(room, kind, nid)
        # Preserve full source evidence. The normalized projection separates relations.
        raw = encode(row)
        view = {k: v for k, v in row.items()
                if k not in {"attachment", "reply_target", "reply_preview", "reply_evidence", "thread"}}
        if kind == "message":
            view["visibility_semantics"] = "unverified"
        data = encode(view)
        previous = self.db.execute("""SELECT o.data,o.version,o.presence,s.raw,s.source_generation
            FROM objects o JOIN sources s ON s.id=o.id WHERE o.id=?""", (uid,)).fetchone()
        if previous and previous["raw"] == raw and previous["presence"] == "observed":
            if previous["source_generation"] != source_generation:
                self.db.execute("UPDATE sources SET source_generation=? WHERE id=?", (source_generation, uid))
            return False
        version = previous["version"] + 1 if previous else 1
        self.db.execute("""INSERT INTO objects VALUES (?,?,?,?,?,'observed')
            ON CONFLICT(id) DO UPDATE SET data=excluded.data,version=excluded.version,presence=excluded.presence""",
            (uid, kind, nid, data, version))
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
        prior = json.loads(previous["raw"]) if previous else {}
        names = sorted(k for k in set(prior) | set(row) if prior.get(k) != row.get(k))
        self.emit(f"{kind}.{verb}", uid, version, {"historical": historical, "fields": names,
                                                   "presence": "observed"})
        return True

    def note_absent(self, kind, seen):
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
                                          (source, legacy_id)).fetchone()[0], {})

    def legacy_mapping(self, source, legacy_id):
        rows = self.db.execute("SELECT object_id FROM legacy_assertions WHERE source=? AND legacy_id=?",
                               (source, legacy_id)).fetchall()
        return ("unique", rows[0][0]) if len(rows) == 1 else ("ambiguous" if rows else "unmapped", None)

    def translate(self, uid, locale, source_version, text):
        with self.transaction(write=True):
            row = self.db.execute("SELECT version FROM objects WHERE id=? AND kind='message'", (uid,)).fetchone()
            if not row or row["version"] != source_version:
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
                      {"message_id": uid, "locale": locale, "message_version": source_version})
            return True

    def watermark(self):
        return self.db.execute("SELECT coalesce(max(seq),0) FROM events").fetchone()[0]

    def replay(self, generation, after, limit):
        if generation != self.generation:
            raise RepositoryError("Event generation mismatch, request a new snapshot")
        with self.transaction():
            if after > self.watermark():
                raise RepositoryError("Event cursor is ahead of this repository")
            return [{**dict(row), "change": json.loads(row["change"])} for row in self.db.execute(
                "SELECT * FROM events WHERE generation=? AND seq>? ORDER BY seq LIMIT ?",
                (generation, after, limit))]

    def snapshot(self):
        with self.transaction():
            result = {"generation": self.generation, "event_schema_version": 1,
                      "event_seq": self.watermark()}
            for table in ("objects", "replies", "thread_members", "translations", "legacy_assertions"):
                result[table] = [dict(row) for row in self.db.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
            for row in result["objects"]:
                row["data"] = json.loads(row["data"])
            return result

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
