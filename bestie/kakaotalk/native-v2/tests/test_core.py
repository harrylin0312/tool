from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from core.model import MAX_ID, native_id, object_id
from core.repository import Repository, RepositoryError
from core.source import NativeReader, NativeSnapshot, SourceError, attachment_fields, capture
from core.sync import run

FIRST = 9007199254740993
TITLE = "fixture room"
SCHEMA = """
CREATE TABLE NTChatRoom(chatId INTEGER,linkId INTEGER,chatName TEXT);
CREATE TABLE NTOpenLink(linkId INTEGER,linkName TEXT);
CREATE TABLE NTChatMessage(chatId INTEGER, logId INTEGER, msgId INTEGER, authorId INTEGER,
 sentAt INTEGER, message TEXT, attachment TEXT, threadId INTEGER, type INTEGER, status INTEGER,
 scope INTEGER, revision INTEGER, subType INTEGER, contentFlag INTEGER);
CREATE INDEX message_room ON NTChatMessage(chatId,logId);
CREATE TABLE NTUser(userId INTEGER,linkId INTEGER,nickName TEXT,displayName TEXT,friendNickName TEXT);
CREATE TABLE NTChatThread(chatId INTEGER,threadId INTEGER,lastLogId INTEGER,updatedAt INTEGER,count INTEGER);
INSERT INTO NTChatRoom VALUES(10,20,'fixture room'),(11,21,'unrelated room');
INSERT INTO NTUser VALUES(42,20,'fixture author',NULL,NULL),(42,21,'excluded author',NULL,NULL);
INSERT INTO NTChatThread VALUES(10,9007199254740993,9223372036854775807,3,1),(11,99,99,3,1);
"""
INSERT = "INSERT INTO NTChatMessage VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"


class SqliteAdapter:
    def __init__(self, conn):
        self.conn = conn

    def query(self, statement):
        return [dict(row) for row in self.conn.execute(statement)]


class FixtureSource:
    generation = "a"
    captured_ns = 1
    origin_token = None
    stable = True
    short = False

    def __init__(self, file):
        self.file = file

    @contextmanager
    def open(self):
        with closing(sqlite3.connect(self.file.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            reader = NativeReader(SqliteAdapter(db), TITLE, self.generation, lambda: self.stable)
            reader.captured_ns = self.captured_ns
            reader.origin_token = self.origin_token
            if self.short:
                reader.messages = lambda *args, **kwargs: []
            yield reader


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "fixture.sqlite"
        self.writer = sqlite3.connect(self.file)
        self.addCleanup(self.writer.close)
        self.writer.executescript(SCHEMA)
        self.add(FIRST)
        self.add(MAX_ID, room=10, scope=3, thread=FIRST, type_=26,
                 attachment='{"src_logId":9007199254740993,"src_message":"at reply time"}')
        self.add(FIRST, room=11)
        self.writer.commit()
        self.source = FixtureSource(self.file)
        self.repo = Repository(self.root / "repo.sqlite", initialize=True)
        self.addCleanup(self.repo.db.close)

    def add(self, nid, room=10, scope=1, thread=0, type_=1, attachment=None, body="message"):
        self.writer.execute(INSERT, (room, nid, nid, 42, 500, body, attachment, thread,
                                     type_, 0, scope, 0, 0, 0))

    def load(self):
        return run(self.repo, self.source, "import", page=1)

    def test_full_import_preserves_ids_scope_unknown_and_isolation(self):
        self.add(FIRST + 1, type_=733, scope=99)
        self.writer.commit()
        self.assertEqual(self.load()["messages_read"], 3)
        snap = self.repo.snapshot()
        messages = [r for r in snap["objects"] if r["kind"] == "message"]
        self.assertEqual({m["native_id"] for m in messages}, {str(FIRST), str(FIRST + 1), str(MAX_ID)})
        self.assertEqual({m["data"]["scope"] for m in messages}, {1, 3, 99})
        self.assertEqual({m["data"]["type"] for m in messages}, {1, 26, 733})
        self.assertEqual(self.repo.statistics()["objects"], {"author": 1, "message": 3, "thread": 1})
        self.assertEqual({r["name"] for r in (o["data"] for o in snap["objects"] if o["kind"] == "author")},
                         {"fixture author"})
        self.assertEqual(snap["thread_members"][0]["thread_native"], str(FIRST))
        self.assertEqual([q["preview"] for q in snap["replies"] if q["target_native"]], ["at reply time"])
        self.assertTrue(self.repo.verify())

    def test_incremental_new_and_idempotent_restart(self):
        self.writer.execute("DELETE FROM NTChatMessage WHERE logId=?", (MAX_ID,))
        self.writer.commit()
        self.load()
        self.add(FIRST + 100)
        self.writer.commit()
        self.source.captured_ns = 2
        self.assertEqual(run(self.repo, self.source, "sync")["changes"], 1)
        last = self.repo.watermark()
        with Repository(self.root / "repo.sqlite") as reopened:
            self.assertEqual(run(reopened, self.source, "sync")["changes"], 0)
            self.assertEqual(reopened.watermark(), last)
            events = reopened.replay(reopened.generation, 0, 100)
            self.assertFalse(events[-1]["change"]["historical"])
            self.assertTrue(events[0]["change"]["historical"])

    def test_reconcile_finds_low_id_and_old_update(self):
        self.load()
        self.add(FIRST + 1)
        self.writer.execute("UPDATE NTChatMessage SET status=8,revision=2 WHERE chatId=10 AND logId=?", (FIRST,))
        self.writer.commit()
        self.assertEqual(run(self.repo, self.source, "sync", overlap=1)["changes"], 0)
        self.assertEqual(run(self.repo, self.source, "reconcile", page=1)["changes"], 2)
        self.assertEqual(run(self.repo, self.source, "reconcile")["changes"], 0)
        kinds = [r["kind"] for r in self.repo.replay(self.repo.generation, 0, 100)]
        self.assertIn("message.updated", kinds)
        self.assertNotIn("message.retracted", kinds)

    def test_overlap_includes_floor(self):
        self.load()
        self.writer.execute("UPDATE NTChatMessage SET message='edited' WHERE chatId=10 AND logId=?", (FIRST,))
        self.writer.commit()
        self.assertEqual(run(self.repo, self.source, "sync", overlap=2, page=1)["changes"], 1)

    def test_schedule_periodic_reconciliation(self):
        run(self.repo, self.source, "import", clock=lambda: 100)
        self.add(FIRST + 1)
        self.writer.commit()
        self.assertFalse(run(self.repo, self.source, "sync", overlap=1, interval=60, clock=lambda: 159)["full"])
        self.assertTrue(run(self.repo, self.source, "sync", overlap=1, interval=60, clock=lambda: 160)["full"])
        self.assertEqual(self.repo.statistics()["objects"]["message"], 3)

    def test_author_and_thread_mutation_are_independent(self):
        self.load()
        self.writer.executescript("UPDATE NTUser SET nickName='changed' WHERE linkId=20;"
                                  "UPDATE NTChatThread SET count=2 WHERE chatId=10;")
        last = self.repo.watermark()
        self.assertEqual(run(self.repo, self.source, "sync")["changes"], 2)
        self.assertEqual([e["kind"] for e in self.repo.replay(self.repo.generation, last, 10)],
                         ["author.updated", "thread.updated"])

    def test_failed_source_guard_reverts_events_and_state(self):
        self.load()
        initial, cursor = self.repo.snapshot(), self.repo.state()
        self.writer.executescript("UPDATE NTChatMessage SET message='new' WHERE chatId=10;")
        self.source.stable = False
        self.source.captured_ns = 2
        with self.assertRaises(SourceError):
            run(self.repo, self.source, "sync")
        self.assertEqual(self.repo.snapshot(), initial)
        self.assertEqual(self.repo.state(), cursor)

    def test_hard_process_exit_reverts_uncommitted_events(self):
        self.load()
        snap, state = self.repo.snapshot(), self.repo.state()
        code = """
import os, sys
from core.repository import Repository
with Repository(sys.argv[1]) as r, r.transaction(write=True):
    r.put('10', 'message', {'id':'5','body':'uncommitted'}, 'a', False)
    r.save_state('10','20','a',50,'5',0,None)
    os._exit(17)
"""
        proc = subprocess.run([sys.executable, "-c", code, str(self.root / "repo.sqlite")],
                              capture_output=True)
        self.assertEqual(proc.returncode, 17)
        with Repository(self.root / "repo.sqlite") as reopened:
            self.assertEqual(reopened.snapshot(), snap)
            self.assertEqual(reopened.state(), state)
            self.assertTrue(reopened.verify())

    def test_incomplete_upper_bound_rolls_back(self):
        self.source.short = True
        with self.assertRaisesRegex(RepositoryError, "Incomplete"):
            self.load()
        self.assertIsNone(self.repo.state())
        self.assertEqual(self.repo.watermark(), 0)
        self.assertEqual(self.repo.statistics()["objects"], {})

    def test_room_and_schema_guards(self):
        self.writer.executescript("ALTER TABLE NTChatThread DROP COLUMN count;")
        with self.assertRaisesRegex(SourceError, "Incompatible schema"):
            self.load()
        self.assertIsNone(self.repo.state())

    def test_ambiguity_stops_room_lookup(self):
        self.writer.executescript("UPDATE NTChatRoom SET chatName='fixture room' WHERE chatId=11;")
        with self.assertRaisesRegex(SourceError, "exactly once"):
            self.load()

    def test_full_import_rejects_missing_native_id(self):
        self.add(None)
        self.writer.commit()
        with self.assertRaisesRegex(SourceError, "Invalid native log ID"):
            self.load()
        self.assertIsNone(self.repo.state())

    def test_duplicate_id_at_page_boundary_is_rejected(self):
        self.add(FIRST)
        self.writer.commit()
        with self.assertRaisesRegex(SourceError, "duplicate"):
            self.load()
        self.assertEqual(self.repo.watermark(), 0)

    def test_source_generation_recovery_preserves_object_ids(self):
        self.load()
        old = self.repo.snapshot()
        self.source.generation = "replacement"
        with self.assertRaisesRegex(RepositoryError, "generation"):
            run(self.repo, self.source, "sync")
        result = run(self.repo, self.source, "reconcile", accept_source_generation=True)
        self.assertEqual(result["changes"], 0)
        self.assertEqual(self.repo.snapshot(), old)

    def test_detects_replaced_capture_origin(self):
        self.source.origin_token = "old-file"
        self.load()
        self.source.origin_token = "new-file"
        with self.assertRaisesRegex(RepositoryError, "replaced"):
            run(self.repo, self.source, "sync")
        self.source.generation = "new-generation"
        self.assertEqual(run(self.repo, self.source, "reconcile", accept_source_generation=True)["changes"], 0)

    def test_replaced_room_cannot_be_accepted_as_same_room(self):
        self.load()
        self.writer.executescript("UPDATE NTChatRoom SET linkId=29 WHERE chatId=10;")
        self.source.generation = "replacement"
        with self.assertRaisesRegex(RepositoryError, "identity"):
            run(self.repo, self.source, "reconcile", accept_source_generation=True)

    def test_old_snapshot_and_regressing_high_water_rejected(self):
        self.source.captured_ns = 10
        self.load()
        self.source.captured_ns = 9
        with self.assertRaisesRegex(RepositoryError, "older"):
            run(self.repo, self.source, "sync")
        self.source.captured_ns = 11
        self.writer.execute("DELETE FROM NTChatMessage WHERE logId=?", (MAX_ID,))
        self.writer.commit()
        with self.assertRaisesRegex(RepositoryError, "regressed"):
            run(self.repo, self.source, "sync")

    def test_missing_record_is_retained_after_full_reconciliation(self):
        self.load()
        self.writer.execute("DELETE FROM NTChatMessage WHERE chatId=10 AND logId=?", (FIRST,))
        self.writer.commit()
        self.assertEqual(run(self.repo, self.source, "reconcile")["not_observed"], 1)
        self.assertEqual(run(self.repo, self.source, "reconcile")["not_observed"], 0)
        snap = self.repo.snapshot()
        message = next(m for m in snap["objects"] if m["native_id"] == str(FIRST) and m["kind"] == "message")
        self.assertEqual(message["presence"], "not_observed")
        self.assertEqual(message["data"]["body"], "message")

    def test_snapshot_watermark_and_event_pagination(self):
        self.load()
        snap = self.repo.snapshot()
        start = self.repo.replay(snap["generation"], 0, 2)
        rest = self.repo.replay(snap["generation"], start[-1]["seq"], 100)
        self.assertEqual([e["seq"] for e in start + rest], list(range(1, snap["event_seq"] + 1)))
        self.assertTrue(all(e["schema_version"] == 1 for e in start + rest))
        self.assertTrue(all("at reply time" not in json.dumps(e) for e in start + rest))
        self.assertEqual(self.repo.replay(snap["generation"], snap["event_seq"], 10), [])
        for g, after in (("bad", 0), (snap["generation"], snap["event_seq"] + 1)):
            with self.assertRaises(RepositoryError):
                self.repo.replay(g, after, 10)

    def test_reviewed_legacy_ambiguity_never_overwrites(self):
        self.load()
        m1, m2 = [object_id("10", "message", str(i)) for i in (FIRST, MAX_ID)]
        self.assertEqual(self.repo.legacy_mapping("html", "m1"), ("unmapped", None))
        self.repo.map_legacy("html", "m1", m1)
        self.assertEqual(self.repo.legacy_mapping("html", "m1"), ("unique", m1))
        self.repo.map_legacy("html", "m1", m2)
        self.assertEqual(self.repo.legacy_mapping("html", "m1"), ("ambiguous", None))

    def test_legacy_history_kept_as_independent_evidence(self):
        self.load()
        snap = self.repo.snapshot()
        self.repo.preserve_legacy("html-v1", "m1", "legacy-html", {"text": "older observation"})
        self.repo.preserve_legacy("html-v1", "m1", "legacy-html", {"text": "older observation"})
        self.assertEqual(self.repo.db.execute("SELECT count(*) FROM legacy_records").fetchone()[0], 1)
        with self.assertRaises(RepositoryError):
            self.repo.preserve_legacy("html-v1", "m1", "legacy-html", {"text": "conflict"})
        self.assertEqual(self.repo.snapshot(), snap)

    def test_translations_are_versioned_and_replayed_without_body(self):
        self.load()
        uid = object_id("10", "message", FIRST)
        self.assertTrue(self.repo.translate(uid, "zh-Hant", 1, "fixture translated phrase"))
        self.assertFalse(self.repo.translate(uid, "zh-Hant", 1, "fixture translated phrase"))
        self.assertNotIn("fixture translated phrase", json.dumps(self.repo.replay(self.repo.generation, 0, 99)))
        with self.assertRaises(RepositoryError):
            self.repo.translate(uid, "zh-Hant", 2, "stale test")

    def test_one_writer_per_repository(self):
        with Repository(self.root / "repo.sqlite") as second, self.repo.transaction(write=True):
            with self.assertRaises(sqlite3.OperationalError):
                run(second, self.source, "import")

    def test_identifier_validation_and_attachment_precision(self):
        self.assertEqual(native_id(MAX_ID), str(MAX_ID))
        for bad in (True, 0, "-1", "01", "1e6", MAX_ID + 1, 0.01):
            with self.assertRaises(ValueError):
                native_id(bad)
        self.assertEqual(attachment_fields(f'{{"src_logId":{MAX_ID}}}'), (str(MAX_ID), None, "observed"))
        self.assertEqual(attachment_fields('{"src_logId":123.0}')[-1], "unparsed")

    def test_copy_requires_private_directory_and_exclusive_destination(self):
        self.writer.commit()
        target = self.root / "sealed"
        capture(self.file, target, "test-generation")
        self.assertEqual((target / "native.db").read_bytes(), self.file.read_bytes())
        self.assertEqual(json.loads((target / "snapshot.json").read_text())["generation"], "test-generation")
        with self.assertRaises(FileExistsError):
            capture(self.file, target, "no-overwrite")
        (target / "native.db").write_bytes(b"changed")
        with self.assertRaisesRegex(SourceError, "manifest"):
            with NativeSnapshot(target, TITLE, self.file, b"fixture").open():
                self.fail("source should not open")

    def test_repository_migrates_older_supported_schema(self):
        path = self.root / "repo.sqlite"
        generation = self.repo.generation
        self.repo.db.executescript("DROP INDEX idx_thread_members_thread;"
                                  "DROP INDEX idx_events_generation_seq; DROP TABLE legacy_records; ALTER TABLE sync_state DROP COLUMN origin_token; PRAGMA user_version=1;")
        with Repository(path) as opened:
            self.assertEqual(opened.generation, generation)
            self.assertEqual(opened.db.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_repository_rejects_unrelated_database(self):
        with self.assertRaises(RepositoryError):
            Repository(self.file, initialize=True)

    def test_cli_snapshot_is_private_and_no_overwrite(self):
        self.load()
        output = self.root / "private-export.json"
        command = [sys.executable, "-m", "core", "snapshot", "--repo",
                   str(self.root / "repo.sqlite"), "--output", str(output)]
        r = subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertNotIn("fixture author", r.stdout)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(output.read_text())["event_seq"], self.repo.watermark())
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


@unittest.skipUnless(os.environ.get("KAKAO_TEST_SQLCIPHER") and os.environ.get("KAKAO_TEST_SQLCIPHER_CLI"),
                     "Set paths to the approved SQLCipher library and CLI for encrypted fixture")
class EncryptedFixtureTest(unittest.TestCase):
    def test_real_cipher_boundary_with_synthetic_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sealed"
            folder.mkdir()
            db = root / "input.db"
            folder.rmdir()
            client = os.environ["KAKAO_TEST_SQLCIPHER_CLI"]
            fake = b"fixture-p2-only"
            commands = f"PRAGMA key='{fake.decode()}'; PRAGMA cipher_compatibility=3; PRAGMA journal_mode=WAL;\n" + SCHEMA
            commands += f"INSERT INTO NTChatMessage VALUES(10,{MAX_ID},1,42,500,'abc'||char(0)||'def',NULL,0,1,0,1,0,0,0);"
            with subprocess.Popen([client, "-batch", "-bail", str(db)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as writer:
                try:
                    writer.stdin.write(commands + "\n.print READY\n")
                    writer.stdin.flush()
                    for line in writer.stdout:
                        if line.strip() == "READY":
                            break
                    else:
                        self.fail("fixture writer exited early")
                    capture(db, folder, "fixture-cipher")
                    self.assertTrue((folder / "native.db-wal").is_file())
                finally:
                    writer.stdin.close()
            library = Path(os.environ["KAKAO_TEST_SQLCIPHER"])
            source = NativeSnapshot(folder, TITLE, library, fake)
            with Repository(root / "private.sqlite", initialize=True) as repo:
                self.assertEqual(run(repo, source, "import")["messages_read"], 1)
                body = [r["data"]["body"] for r in repo.snapshot()["objects"] if r["kind"] == "message"]
                self.assertEqual(body, ["abc\0def"])
                before = repo.snapshot()
                with self.assertRaises(SourceError):
                    run(repo, NativeSnapshot(folder, TITLE, library, b"wrong"), "sync")
                self.assertEqual(repo.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
