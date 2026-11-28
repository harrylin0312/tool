"""Query a sealed KakaoTalk SQLCipher copy. The app's live database is never opened."""
from contextlib import contextmanager
import ctypes as c
import hashlib
import json
import os
import time
from pathlib import Path

from .model import native_id, optional_id

TABLES = {
    "NTChatRoom": "chatId linkId chatName",
    "NTOpenLink": "linkId linkName",
    "NTChatMessage": "chatId logId msgId authorId sentAt message attachment threadId type status scope revision subType contentFlag",
    "NTUser": "userId linkId nickName displayName friendNickName",
    "NTChatThread": "chatId threadId lastLogId updatedAt count",
}
MESSAGE = """SELECT CAST(logId AS TEXT) id, CAST(msgId AS TEXT) message_index,
 CAST(authorId AS TEXT) author, sentAt sent_at, message body, attachment,
 CAST(threadId AS TEXT) thread, type, status, scope, revision, subType subtype,
 contentFlag content_flag FROM NTChatMessage WHERE chatId = {room}"""


class SourceError(RuntimeError):
    pass


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def snapshot_files(directory):
    return {name: directory / name for name in ("native.db", "native.db-wal")}


def clean_directory(directory):
    directory = directory.resolve(strict=True)
    if "com.kakao.KakaoTalkMac" in directory.parts:
        raise SourceError("The KakaoTalk container cannot be used as a snapshot directory")
    return directory


def file_state(directory):
    out = {}
    for name, path in snapshot_files(directory).items():
        if path.is_symlink():
            raise SourceError("Snapshot files must not be symbolic links")
        if path.exists():
            st = path.stat()
            if not path.is_file() or st.st_nlink != 1:
                raise SourceError("Snapshot files must be independent regular files")
            out[name] = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    shared = directory / "native.db-shm"
    if shared.is_symlink() or (shared.exists() and (not shared.is_file() or shared.stat().st_nlink != 1)):
        raise SourceError("Invalid snapshot shared-memory sidecar")
    if "native.db" not in out or out["native.db"][2] == 0:
        raise SourceError("Missing or empty snapshot database")
    return out


def seal(directory, generation, *, origin_token=None, sign=None):
    directory = clean_directory(directory)
    if not generation.strip():
        raise SourceError("Source generation must be nonempty")
    before = file_state(directory)
    files = {name: digest(directory / name) for name in before}
    if file_state(directory) != before:
        raise SourceError("Snapshot changed during sealing")
    manifest = {"version": 1, "generation": generation, "captured_ns": time.time_ns(),
                "origin_token": origin_token, "sha256": files}
    if sign:
        manifest["receipt"] = sign(manifest)
    fd = os.open(directory / "snapshot.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(manifest, handle)
        handle.flush()
        os.fsync(handle.fileno())


class Cipher:
    """Small binding to the already authorized SQLCipher library."""

    def __init__(self, library, path, key):
        self.api = c.CDLL(str(library))
        self.db = c.c_void_p()
        api = self.api
        api.sqlite3_open_v2.argtypes = [c.c_char_p, c.POINTER(c.c_void_p), c.c_int, c.c_char_p]
        api.sqlite3_close.argtypes = [c.c_void_p]
        api.sqlite3_key.argtypes = [c.c_void_p, c.c_void_p, c.c_int]
        api.sqlite3_prepare_v2.argtypes = [c.c_void_p, c.c_char_p, c.c_int,
                                           c.POINTER(c.c_void_p), c.POINTER(c.c_char_p)]
        api.sqlite3_step.argtypes = [c.c_void_p]
        api.sqlite3_finalize.argtypes = [c.c_void_p]
        api.sqlite3_column_count.argtypes = [c.c_void_p]
        api.sqlite3_column_name.argtypes = [c.c_void_p, c.c_int]
        api.sqlite3_column_name.restype = c.c_char_p
        api.sqlite3_column_text.argtypes = [c.c_void_p, c.c_int]
        api.sqlite3_column_text.restype = c.c_void_p
        api.sqlite3_column_bytes.argtypes = [c.c_void_p, c.c_int]
        api.sqlite3_column_type.argtypes = [c.c_void_p, c.c_int]
        try:
            if api.sqlite3_open_v2(os.fsencode(path), c.byref(self.db), 1, None):
                raise SourceError("Cannot open snapshot read-only")
            if not key or api.sqlite3_key(self.db, key, len(key)):
                raise SourceError("SQLCipher key configuration failed")
            self.query("PRAGMA cipher_compatibility=3")
            self.query("PRAGMA query_only=ON")
            if self.query("PRAGMA query_only") != [{"query_only": "1"}]:
                raise SourceError("query_only was not enabled")
        except BaseException:
            self.close()
            raise

    def query(self, statement):
        api = self.api
        prepared = c.c_void_p()
        tail = c.c_char_p()
        sql = c.create_string_buffer(statement.encode())
        code = api.sqlite3_prepare_v2(self.db, c.cast(sql, c.c_char_p), -1,
                                      c.byref(prepared), c.byref(tail))
        if code:
            raise SourceError(f"SQLCipher prepare failed ({code})")
        rows = []
        try:
            if tail.value and tail.value.strip():
                raise SourceError("Expected one SQL statement")
            fields = [api.sqlite3_column_name(prepared, i).decode()
                      for i in range(api.sqlite3_column_count(prepared))]
            while (code := api.sqlite3_step(prepared)) == 100:
                row = {}
                for i, name in enumerate(fields):
                    if api.sqlite3_column_type(prepared, i) == 5:
                        row[name] = None
                    else:
                        ptr = api.sqlite3_column_text(prepared, i)
                        row[name] = c.string_at(ptr, api.sqlite3_column_bytes(prepared, i)).decode()
                rows.append(row)
            if code != 101:
                raise SourceError(f"SQLCipher query failed ({code})")
        finally:
            api.sqlite3_finalize(prepared)
        return rows

    def close(self):
        if self.db:
            self.api.sqlite3_close(self.db)
            self.db = c.c_void_p()


class NativeSnapshot:
    def __init__(self, path, title, library, key):
        self.path = path
        self.title = title
        self.library = library
        self.key = key

    @contextmanager
    def open(self):
        path = clean_directory(self.path)
        control = path / "snapshot.json"
        if control.is_symlink():
            raise SourceError("Manifest must not be a symbolic link")
        with control.open() as handle:
            manifest = json.load(handle)
        generation = manifest.get("generation")
        if (manifest.get("version") != 1 or not isinstance(generation, str) or not generation.strip()
                or type(manifest.get("captured_ns")) is not int or manifest["captured_ns"] <= 0):
            raise SourceError("Invalid snapshot manifest")
        before = file_state(path)
        if manifest.get("sha256") != {name: digest(path / name) for name in before}:
            raise SourceError("Snapshot content differs from manifest")
        if before != file_state(path):
            raise SourceError("Snapshot changed before opening")
        db = Cipher(self.library, path / "native.db", self.key)
        try:
            db.query("BEGIN")
            reader = NativeReader(db, self.title, generation, lambda: before == file_state(path))
            reader.manifest = manifest
            reader.captured_ns = manifest["captured_ns"]
            reader.origin_token = manifest.get("origin_token")
            if reader.origin_token is not None and not isinstance(reader.origin_token, str):
                raise SourceError("Invalid snapshot origin token")
            yield reader
        finally:
            db.close()


def integer(value):
    return None if value is None else int(value)


def attachment_fields(raw):
    if raw is None:
        return None, None, "absent"
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or "src_logId" not in value:
            return None, None, "absent"
        preview = value.get("src_message")
        return native_id(value["src_logId"]), preview if isinstance(preview, str) else None, "observed"
    except (ValueError, TypeError):
        return None, None, "unparsed"


class NativeReader:
    def __init__(self, db, title, generation, is_stable):
        self.db = db
        self.generation = generation
        self.is_stable = is_stable
        for table, columns in TABLES.items():
            seen = {row["name"] for row in db.query(f"PRAGMA table_info({table})")}
            if not set(columns.split()) <= seen:
                raise SourceError(f"Incompatible schema in {table}")
        if not title or "\0" in title:
            raise SourceError("Invalid room title")
        label = "'" + title.replace("'", "''") + "'"
        matches = db.query(f"""SELECT CAST(r.chatId AS TEXT) room, CAST(r.linkId AS TEXT) link
            FROM NTChatRoom r WHERE r.linkId > 0 AND
            (r.chatName={label} OR EXISTS(SELECT 1 FROM NTOpenLink o
                WHERE o.linkId=r.linkId AND o.linkName={label}))""")
        if len(matches) != 1:
            raise SourceError("Target Open Chat must match exactly once")
        self.room = native_id(matches[0]["room"])
        self.link = native_id(matches[0]["link"])
        self.identity = (self.room, self.link)
        self.select = MESSAGE.format(room=self.room)
    def latest(self):
        row = self.db.query(f"SELECT CAST(max(logId) AS TEXT) value FROM NTChatMessage WHERE chatId={self.room}")[0]
        return optional_id(row["value"])

    def validate_full(self):
        if self.db.query(f"""SELECT 1 FROM NTChatMessage WHERE chatId={self.room}
                            AND (typeof(logId)<>'integer' OR logId<=0) LIMIT 1"""):
            raise SourceError("Invalid native log ID in target room")

    def recent_floor(self, cursor, count):
        result = self.db.query(f"""SELECT CAST(logId AS TEXT) id FROM NTChatMessage
            WHERE chatId={self.room} AND logId<={native_id(cursor)}
            ORDER BY logId DESC LIMIT {count}""")
        return result[-1]["id"] if result else None

    def messages(self, after, upper, limit, *, include_floor=False):
        if upper is None:
            return []
        where = f" AND logId<={native_id(upper)}"
        if after is not None:
            comparator = ">=" if include_floor else ">"
            where += f" AND logId{comparator}{native_id(after)}"
        result = []
        page = self.db.query(self.select + where + f" ORDER BY logId LIMIT {limit + 1}")
        if any(a["id"] == b["id"] for a, b in zip(page, page[1:])):
            raise SourceError("Ambiguous duplicate native log ID")
        for row in page[:limit]:
            target, preview, status = attachment_fields(row["attachment"])
            row.update(id=native_id(row["id"]), author=optional_id(row["author"]),
                       thread=optional_id(row["thread"]), reply_target=target,
                       reply_preview=preview, reply_evidence=status)
            for name in ("sent_at", "type", "status", "scope", "revision", "subtype", "content_flag"):
                row[name] = integer(row[name])
            result.append(row)
        return result

    def authors(self):
        return [{**row, "id": native_id(row["id"])} for row in self.db.query(f"""
            SELECT CAST(userId AS TEXT) id, coalesce(nullif(nickName,''), nullif(displayName,''), friendNickName) name
            FROM NTUser WHERE linkId={self.link} ORDER BY userId""")]

    def threads(self):
        return [{**row, "id": native_id(row["id"]), "last": optional_id(row["last"]),
                 "updated_at": integer(row["updated_at"]), "count": integer(row["count"])}
                for row in self.db.query(f"""SELECT CAST(threadId AS TEXT) id,
                CAST(lastLogId AS TEXT) last, updatedAt updated_at, count
                FROM NTChatThread WHERE chatId={self.room} ORDER BY threadId""")]

    def verify(self):
        if not self.is_stable():
            raise SourceError("Snapshot changed during synchronization")


def capture(source, destination, generation, *, sign=None):
    """Copy a stable main/WAL pair without opening the source via SQLite."""
    import shutil

    source = source.resolve(strict=True)
    dst = destination.absolute()
    if "com.kakao.KakaoTalkMac" in dst.resolve().parts:
        raise SourceError("Capture destination must be outside the KakaoTalk container")
    paths = {name: source.with_name(source.name + suffix)
             for name, suffix in (("native.db", ""), ("native.db-wal", "-wal"))}

    def observe():
        result = {}
        for name, path in paths.items():
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise SourceError("Capture source must be a regular file")
            st = path.stat()
            result[name] = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, digest(path))
        if "native.db" not in result:
            raise SourceError("Capture source is unavailable")
        return result

    dst.mkdir(mode=0o700)
    try:
        before = observe()
        for name in before:
            with paths[name].open("rb") as incoming, (dst / name).open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        if observe() != before or any(digest(dst / name) != info[-1] for name, info in before.items()):
            raise SourceError("Source changed during capture; retry or use a quiescent source")
        source_identity = before["native.db"][:2]
        origin_token = hashlib.sha256(repr(source_identity).encode()).hexdigest()
        seal(dst, generation, origin_token=origin_token, sign=sign)
    except BaseException:
        shutil.rmtree(dst)
        raise
