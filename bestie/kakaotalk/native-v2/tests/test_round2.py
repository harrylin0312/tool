from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from core.model import object_id

from core.repository import Repository, RepositoryError
from core.witness import WitnessError


class RoundTwoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "repo.sqlite"
        self.repo = Repository(self.path, initialize=True)
        self.addCleanup(self.repo.db.close)

    def legacy(self, source, key, precision="second"):
        self.repo.preserve_legacy(source, key, "app-export", {"private": True})
        stamp = "2026-11-25T22:00:05+08:00" if precision == "second" else "2026-11-25T22:00:00+08:00"
        return self.repo.publish_legacy(source, key, body="same", author="fixture author",
                                        timestamp=stamp, precision=precision, confidence="reviewed", reviewed=True)

    def test_same_source_distinct_ids_survive_equal_and_overlapping_times(self):
        expected = {self.legacy("export", "one"), self.legacy("export", "two"),
                    self.legacy("export", "three", "minute")}
        self.assertEqual({x["id"] for x in self.repo.snapshot()["legacy"]}, expected)

    def test_unique_native_match_becomes_ambiguous_when_identity_count_grows(self):
        with self.repo.transaction(write=True):
            self.repo.put("10", "author", {"id":"1", "name":"fixture author"}, "source", False)
            self.repo.put("10", "message", {"id":"100", "author":"1", "body":"same",
                                           "sent_at":int(datetime.fromisoformat("2026-11-25T22:00:05+08:00").timestamp())}, "source", False)
        first = self.legacy("export", "one")
        self.assertEqual(self.repo.snapshot()["legacy"], [])
        second = self.legacy("export", "two", "minute")
        self.assertEqual({r["id"]:r["data"]["mapping_state"] for r in self.repo.snapshot()["legacy"]},
                         {first:"ambiguous", second:"ambiguous"})
        third = self.legacy("other export", "one")
        self.assertEqual(len(self.repo.snapshot()["legacy"]), 3)
        target = object_id("10", "message", "100")
        self.repo.map_legacy("export", "one", target)
        self.assertEqual({r["id"] for r in self.repo.snapshot()["legacy"]}, {second, third})
        self.repo.map_legacy("export", "two", target)
        self.assertEqual({r["id"]:r["data"]["mapping_state"] for r in self.repo.snapshot()["legacy"]},
                         {first:"ambiguous", second:"ambiguous", third:"ambiguous"})

    def test_first_open_repairs_existing_hidden_history_and_advances_watermark(self):
        self.legacy("export", "one")
        hidden = self.legacy("export", "two")
        with self.repo.transaction(write=True):
            self.repo.db.execute("DELETE FROM metadata WHERE key='legacy_projection_policy'")
            self.repo.db.execute("UPDATE legacy_views SET visible=0 WHERE id=?", (hidden,))
        start = self.repo.watermark()
        with Repository(self.path) as reopened:
            self.assertEqual(len(reopened.snapshot()["legacy"]), 2)
            self.assertGreater(reopened.watermark(), start)
            last = reopened.watermark()
        with Repository(self.path) as reopened:
            self.assertEqual(reopened.watermark(), last)

    def crash(self, *, spill=False):
        code = """
import os, sys
from core.repository import Repository
with Repository(sys.argv[1]) as repo:
    saved = repo.witness.write
    def crash(record):
        saved(record)
        if record.get("pending"):
            os._exit(71)
    repo.witness.write = crash
    with repo.transaction(write=True):
        spill = sys.argv[2] == "True"
        repo.db.execute("PRAGMA cache_size=8" if spill else "PRAGMA cache_size=1000")
        body = "abandoned" * (30000 if spill else 1)
        repo.put("10", "message", {"id":"400", "body":body}, "source", False)
"""
        return subprocess.run([sys.executable, "-c", code, str(self.path), str(spill)], capture_output=True).returncode

    def test_restore_recovers_abandoned_journal_under_pending_witness(self):
        with self.repo.transaction(write=True):
            self.repo.put("10", "message", {"id":"100", "body":"saved"}, "source", False)
        old = self.repo.snapshot()
        backup = self.path.with_name("backup.sqlite")
        self.repo.backup(backup)
        self.assertEqual(self.crash(), 71)
        journal = self.path.with_name(self.path.name + "-journal")
        self.assertTrue(journal.exists())
        with self.assertRaises(WitnessError):
            Repository(self.path)
        self.assertTrue(journal.exists())
        generation = Repository.restore(self.path, backup)
        self.assertNotEqual(generation, old["generation"])
        self.assertFalse(journal.exists())
        with Repository(self.path) as restored:
            self.assertTrue(restored.verify())
            self.assertEqual(restored.snapshot()["objects"], old["objects"])
            with self.assertRaises(RepositoryError):
                restored.replay(old["generation"], old["event_seq"], 10)
            self.assertEqual(restored.changes(old["generation"], old["event_seq"])["mode"], "snapshot")

    def test_direct_restore_performs_hot_rollback_without_prior_reopen(self):
        backup = self.path.with_name("backup.sqlite")
        self.repo.backup(backup)
        self.assertEqual(self.crash(spill=True), 71)
        journal = self.path.with_name(self.path.name + "-journal")
        self.assertTrue(journal.exists())
        with journal.open("rb") as handle:
            self.assertEqual(handle.read(8), bytes.fromhex("d9d505f920a163d7"))
        self.assertNotEqual(Repository.restore(self.path, backup), self.repo.generation)
        with Repository(self.path) as restored:
            self.assertTrue(restored.verify())
            self.assertEqual(restored.snapshot()["objects"], [])
        self.assertFalse(journal.exists())

    def test_recovered_endpoint_outside_witness_is_refused(self):
        backup = self.path.with_name("backup.sqlite")
        self.repo.backup(backup)
        self.assertEqual(self.crash(), 71)
        with self.repo.witness.locked():
            witnessed = self.repo.witness.read()
            witnessed["committed"]["tail"] = "unexpected"
            self.repo.witness.write(witnessed)
        with self.assertRaisesRegex(WitnessError, "neither|either"):
            Repository.restore(self.path, backup)
        self.assertEqual(self.repo.witness.read(), witnessed)
