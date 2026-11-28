from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.authority import bind, trusted_capture
from core.batch import page
from core.model import MAX_ID, native_id, object_id
from core.repository import MIGRATIONS, Repository, RepositoryError
from core.witness import WitnessError
from core.source import NativeReader, NativeSnapshot, SourceError, attachment_fields, capture, seal
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
    counter = 0
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
            self.counter += 1
            reader.manifest = {"fixture_counter": self.counter}
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
        # Engine-only fixtures emulate the trusted capture adapter. Encrypted tests below
        # exercise real receipts and refusal of an externally resealed copy.
        auth = patch("core.sync.authenticate", side_effect=lambda _, m: (
            m["fixture_counter"], str(m["fixture_counter"])))
        auth.start()
        self.addCleanup(auth.stop)
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
        self.assertTrue(all(e["schema_version"] == 2 for e in start + rest))
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
            with self.assertRaises(WitnessError):
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
        path = self.root / "v1.sqlite"
        with closing(sqlite3.connect(path)) as old:
            old.executescript(MIGRATIONS[0] + "PRAGMA user_version=1;")
            old.executemany("INSERT INTO metadata VALUES (?,?)",
                            [("format", "kakao-native-v2"), ("generation", "old-generation")])
            old.commit()
        with self.assertRaises(WitnessError):
            Repository(path)
        with Repository(path, adopt=True) as opened:
            self.assertNotEqual(opened.generation, "old-generation")
            self.assertEqual(opened.db.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(opened._meta("repository_id"), "old-generation")
            self.assertTrue(opened.verify())

    def test_v3_adoption_keeps_active_translation_and_old_bookmarks(self):
        path = self.root / "v3.sqlite"
        uid = object_id("10", "message", FIRST)
        with closing(sqlite3.connect(path)) as old:
            old.executescript("".join(MIGRATIONS[:3]) + "PRAGMA user_version=3;")
            old.executemany("INSERT INTO metadata VALUES (?,?)",
                            [("format", "kakao-native-v2"), ("generation", "legacy-generation")])
            old.execute("INSERT INTO objects VALUES (?,?,?,?,?,?)",
                        (uid, "message", str(FIRST), '{"body":"old"}', 2, "observed"))
            old.execute("INSERT INTO translations VALUES (?,?,?,?,?)", (uid, "zh-Hant", 2, "old translation", 1))
            old.execute("INSERT INTO legacy_assertions VALUES (?,?,?)", ("legacy", "m1", uid))
            old.commit()
        with Repository(path, adopt=True) as migrated:
            snapshot = migrated.snapshot()
            self.assertNotEqual(snapshot["generation"], "legacy-generation")
            self.assertEqual(snapshot["objects"][0]["input_version"], 2)
            self.assertEqual(snapshot["translations"][0]["text"], "old translation")
            self.assertEqual(migrated.legacy_mapping("legacy", "m1"), ("unique", uid))

    def test_repository_rejects_unrelated_database(self):
        with self.assertRaises(RepositoryError):
            Repository(self.file, initialize=True)

    def test_translation_input_version_only_changes_with_body(self):
        self.load()
        uid = object_id("10", "message", FIRST)
        self.assertTrue(self.repo.translate(uid, "zh-Hant", 1, "first version"))
        self.writer.execute("UPDATE NTChatMessage SET status=2, scope=3, attachment=? WHERE chatId=10 AND logId=?",
                            ('{"src_logId":9223372036854775807}', FIRST))
        self.writer.commit()
        run(self.repo, self.source, "sync")
        item = next(m for m in self.repo.snapshot()["objects"] if m["id"] == uid)
        self.assertEqual((item["version"], item["input_version"]), (2, 1))
        self.assertEqual(self.repo.snapshot()["translations"][0]["original_version"], 1)
        self.assertFalse(self.repo.translate(uid, "zh-Hant", 1, "first version"))
        self.writer.execute("UPDATE NTChatMessage SET message='edited' WHERE chatId=10 AND logId=?", (FIRST,))
        self.writer.commit()
        run(self.repo, self.source, "sync")
        with self.assertRaises(RepositoryError):
            self.repo.translate(uid, "zh-Hant", 1, "stale overwrite")
        self.assertTrue(self.repo.translate(uid, "zh-Hant", 2, "second version"))
        self.assertEqual(len(self.repo.snapshot()["translations"]), 1)
        self.assertEqual(self.repo.db.execute("SELECT count(*) FROM translations").fetchone()[0], 2)

    def reviewed_history(self, source, key, body="historical only", author="reviewed author",
                         when="2026-11-25T22:00:00+08:00", precision="minute"):
        self.repo.preserve_legacy(source, key, "legacy-html", {"raw": "private evidence"})
        return self.repo.publish_legacy(source, key, body=body, author=author, timestamp=when,
                                        precision=precision, confidence="reviewed", reviewed=True)

    def test_legacy_projection_moves_watermark_and_whitelists_fields(self):
        self.load()
        seq = self.repo.watermark()
        uid = self.reviewed_history("legacy a", "m1")
        view = self.repo.snapshot()
        self.assertGreater(view["event_seq"], seq)
        self.assertEqual(view["legacy"][0]["id"], uid)
        self.assertEqual(view["legacy"][0]["data"]["precision"], "minute")
        self.assertNotIn("private evidence", json.dumps(view))
        seq2 = view["event_seq"]
        self.reviewed_history("legacy a", "m1")
        self.assertEqual(self.repo.watermark(), seq2)
        self.reviewed_history("legacy a", "m1", body="historical correction")
        delta = self.repo.changes(self.repo.generation, seq2)
        self.assertTrue(delta["replace_legacy_and_mappings"])
        self.assertEqual(delta["records"][0]["value"]["data"]["body"], "historical correction")

    def test_duplicate_history_suppression_and_mapping_removal(self):
        self.load()
        uid = self.reviewed_history("legacy a", "m1")
        self.reviewed_history("legacy b", "m2")
        self.assertEqual([x["id"] for x in self.repo.snapshot()["legacy"]], [uid])
        self.reviewed_history("legacy c", "m3", body="message", author="fixture author",
                              when="1970-01-01T00:08:20+00:00", precision="second")
        self.assertEqual(len(self.repo.snapshot()["legacy"]), 1)
        before = self.repo.watermark()
        self.repo.map_legacy("legacy a", "m1", object_id("10", "message", FIRST))
        delta = self.repo.changes(self.repo.generation, before)
        self.assertTrue(delta["replace_legacy_and_mappings"])
        self.assertTrue(all(x["value"].get("id") != uid for x in delta["records"]))
        self.assertEqual(len(self.repo.snapshot()["legacy"]), 0)

    def test_native_arrival_suppresses_previously_published_legacy_row(self):
        self.load()
        uid = self.reviewed_history("legacy a", "m1", body="late", author="fixture author",
                                    when="1970-01-01T00:08:20+00:00", precision="second")
        self.assertEqual([v["id"] for v in self.repo.snapshot()["legacy"]], [uid])
        seq = self.repo.watermark()
        self.add(FIRST + 1, body="late")
        self.writer.commit()
        run(self.repo, self.source, "reconcile")
        self.assertEqual(self.repo.snapshot()["legacy"], [])
        self.assertTrue(self.repo.changes(self.repo.generation, seq)["replace_legacy_and_mappings"])

    def test_three_updates_collapse_and_pages_keep_watermark(self):
        self.load()
        start = self.repo.watermark()
        for status in (1, 2, 3):
            self.writer.execute("UPDATE NTChatMessage SET status=? WHERE chatId=10 AND logId=?", (status, FIRST))
            self.writer.commit()
            run(self.repo, self.source, "sync")
        self.writer.executescript("UPDATE NTUser SET nickName='new' WHERE linkId=20;")
        run(self.repo, self.source, "sync")
        batch = self.repo.changes(self.repo.generation, start)
        self.assertEqual(len(batch["records"]), 2)
        self.assertEqual(batch["end"], start + 4)
        msg = next(x["value"]["object"] for x in batch["records"] if x["value"]["object"]["kind"]=="message")
        self.assertEqual((msg["version"],msg["data"]["status"]),(4,3))
        first = page(batch, 0, 1)
        self.writer.executescript("UPDATE NTUser SET nickName='newer' WHERE linkId=20;")
        run(self.repo, self.source, "sync")
        second = page(batch, first["next_offset"], 1)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(first["records"] + second["records"], batch["records"])
        self.assertEqual(second, page(batch, first["next_offset"], 1))
        self.assertEqual(first["end"], second["end"])
        self.assertEqual(self.repo.changes(self.repo.generation, second["end"])["end"], second["end"] + 1)
        self.assertEqual(self.repo.changes("wrong-generation", start)["mode"], "snapshot")
        self.assertEqual(self.repo.changes(self.repo.generation, self.repo.watermark()+1)["reset_reason"],
                         "history_unavailable")

    def test_paged_client_transaction_retry_does_not_advance_halfway(self):
        self.load()
        batch = self.repo.changes("bootstrap", 0)
        first = page(batch, 0, 2)
        second = page(batch, first["next_offset"], 100)
        self.assertIsNone(second["next_offset"])
        with closing(sqlite3.connect(":memory:")) as client:
            client.executescript("CREATE TABLE objects(id TEXT PRIMARY KEY);"
                                 "CREATE TABLE state(seq INTEGER); INSERT INTO state VALUES (0);")

            def apply(fail):
                self.assertEqual(first["batch_id"], second["batch_id"])
                self.assertEqual(first["next_offset"], second["offset"])
                self.assertEqual(first["length"], len(first["records"] + second["records"]))
                with client:
                    for i, record in enumerate(first["records"] + second["records"]):
                        uid = record["value"]["object"]["id"]
                        client.execute("INSERT INTO objects VALUES (?)", (uid,))
                        if fail and i == 1:
                            raise RuntimeError("interrupted before cursor commit")
                    client.execute("UPDATE state SET seq=?", (second["end"],))

            with self.assertRaises(RuntimeError):
                apply(True)
            self.assertEqual(client.execute("SELECT seq FROM state").fetchone()[0], 0)
            self.assertEqual(client.execute("SELECT count(*) FROM objects").fetchone()[0], 0)
            apply(False)
            self.assertEqual(client.execute("SELECT seq FROM state").fetchone()[0], batch["end"])
            self.assertEqual(client.execute("SELECT count(*) FROM objects").fetchone()[0], len(batch["records"]))

    def test_old_file_cannot_reuse_witness_and_restore_rotates(self):
        self.load()
        uid = object_id("10", "message", FIRST)
        self.repo.translate(uid, "zh-Hant", 1, "retained translation")
        self.repo.map_legacy("html", "m1", uid)
        backup = self.root / "backup.sqlite"
        self.repo.backup(backup)
        original_generation = self.repo.generation
        self.writer.executescript("UPDATE NTChatMessage SET status=8 WHERE chatId=10;")
        run(self.repo, self.source, "sync")
        high = self.repo.watermark()
        earlier = self.root / "earlier.sqlite"
        shutil.copyfile(backup, earlier)
        os.replace(earlier, self.repo.path)
        with self.assertRaises(WitnessError):
            Repository(self.repo.path)
        generation = Repository.restore(self.repo.path, backup)
        self.assertNotEqual(generation, original_generation)
        with Repository(self.repo.path) as restored:
            snap = restored.snapshot()
            self.assertEqual(snap["event_seq"], 0)
            self.assertEqual(snap["translations"][0]["text"], "retained translation")
            self.assertEqual(restored.legacy_mapping("html", "m1"), ("unique", uid))
            for value in (1,2,3):
                self.writer.execute("UPDATE NTChatMessage SET status=? WHERE chatId=10", (value,))
                self.writer.commit()
                run(restored, self.source, "sync")
            self.assertGreaterEqual(restored.watermark(), high)
            with self.assertRaises(RepositoryError):
                restored.replay(original_generation, high, 100)
            self.assertEqual(restored.changes(original_generation, high)["reset_reason"], "generation_mismatch")

    @patch("core.repository.now", return_value="same-clock-fixture")
    def test_equal_sequence_different_history_is_rejected(self, _now):
        self.load()
        fork = self.root / "fork.sqlite"
        self.repo.backup(fork)
        fork_witness = fork.with_name(fork.name + ".witness")
        shutil.copyfile(self.repo.witness.path, fork_witness)
        fork_witness.chmod(0o600)
        counter = self.source.counter
        self.writer.executescript("UPDATE NTChatMessage SET status=1 WHERE chatId=10;")
        run(self.repo, self.source, "sync")
        trusted = self.repo.watermark()
        self.source.counter = counter
        self.writer.executescript("UPDATE NTChatMessage SET status=2 WHERE chatId=10;")
        with Repository(fork) as other:
            run(other, self.source, "sync")
            self.assertEqual(other.watermark(), trusted)
        os.replace(fork, self.repo.path)
        with self.assertRaisesRegex(WitnessError, "history"):
            Repository(self.repo.path)

    def test_witness_pending_crash_paths(self):
        self.load()
        with self.repo.witness.locked():
            valid = self.repo.witness.read()
            valid["pending"] = valid["committed"]
            self.repo.witness.write(valid)
        self.assertTrue(self.repo.verify())
        with self.repo.witness.locked():
            valid = self.repo.witness.read()
            self.assertIsNone(valid["pending"])
            valid["pending"] = {**valid["committed"], "seq": self.repo.watermark()+1}
            self.repo.witness.write(valid)
        with self.assertRaises(WitnessError):
            self.repo.snapshot()

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


    def test_bound_capture_accepts_normal_edit_and_rejects_resealed_old_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "app.db"
            library = Path(os.environ["KAKAO_TEST_SQLCIPHER"])
            tool = os.environ["KAKAO_TEST_SQLCIPHER_CLI"]
            fake = b"fixture-freshness"
            def mutate(sql):
                prefix = "PRAGMA key='fixture-freshness'; PRAGMA cipher_compatibility=3;"
                subprocess.run([tool, "-batch", "-bail", str(app)], input=prefix+sql,
                               capture_output=True, text=True, check=True)
            mutate(SCHEMA + f"INSERT INTO NTChatMessage VALUES(10,{FIRST},1,42,500,'A',NULL,0,1,0,1,0,0,0);")
            def src(folder):
                return NativeSnapshot(folder, TITLE, library, fake)
            with Repository(root / "repo.sqlite", initialize=True) as repo:
                bind(repo, app, "a")
                old = root / "first"
                trusted_capture(repo, app, old, "a")
                run(repo, src(old), "import")
                mutate("UPDATE NTChatMessage SET message='B';")
                newer = root / "second"
                trusted_capture(repo, app, newer, "a")
                self.assertEqual(run(repo, src(newer), "sync")["changes"], 1)
                self.assertEqual(run(repo, src(newer), "sync")["changes"], 0)
                previous = repo.snapshot()
                with self.assertRaises(SourceError):
                    run(repo, src(old), "sync")
                resealed = root / "resealed"
                resealed.mkdir()
                shutil.copyfile(old / "native.db", resealed / "native.db")
                seal(resealed, "a")
                with self.assertRaisesRegex(RepositoryError, "Untrusted"):
                    run(repo, src(resealed), "sync")
                forged = json.loads((resealed / "snapshot.json").read_text())
                forged["receipt"] = json.loads((newer / "snapshot.json").read_text())["receipt"]
                (resealed / "snapshot.json").write_text(json.dumps(forged))
                with self.assertRaises(SourceError):
                    run(repo, src(resealed), "sync")
                self.assertEqual(repo.snapshot(), previous)
                external = root / "authorized-external"
                external.mkdir()
                shutil.copyfile(old / "native.db", external / "native.db")
                seal(external, "explicit-recovery")
                with self.assertRaisesRegex(RepositoryError, "Untrusted"):
                    run(repo, src(external), "reconcile", accept_source_generation=True)
                result = run(repo, src(external), "reconcile", accept_source_generation=True,
                             recover_external=True)
                self.assertEqual(result["changes"], 1)


if __name__ == "__main__":
    unittest.main()
