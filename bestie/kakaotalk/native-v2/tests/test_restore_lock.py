from contextlib import contextmanager
import select
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from core.repository import Repository, RepositoryError
from core.witness import WitnessError


READER = """
import sqlite3, sys
with sqlite3.connect(sys.argv[1], isolation_level=None, timeout=0) as db:
    db.execute(sys.argv[2])
    print(db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0], flush=True)
    sys.stdin.readline()
    print(db.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0], flush=True)
"""

TRY_SQLITE = """
import sqlite3, sys
db=sqlite3.connect(sys.argv[1], timeout=0)
try:
    db.execute(sys.argv[2])
    db.execute("SELECT value FROM metadata").fetchall()
except sqlite3.OperationalError as exc:
    assert exc.sqlite_errorcode == sqlite3.SQLITE_BUSY, exc
    print("busy")
else:
    print("opened")
finally:
    db.close()
"""

RESTORE = """
import os, sys
from pathlib import Path
from core.repository import Repository
from core.witness import Witness
path, backup = map(Path, sys.argv[1:3])
phase = sys.argv[3]

def boundary():
    print("ready", flush=True)
    if phase.startswith("crash"):
        os._exit(71)
    assert sys.stdin.readline().strip() == "resume"

original = os.replace
def swap(source, dest):
    if Path(dest) == path and phase in ("before", "crash-before"):
        boundary()
    original(source, dest)
    if Path(dest) == path and phase in ("after", "crash-after"):
        boundary()

os.replace = swap
print(Repository.restore(path, backup), flush=True)
"""


class RestoreLockTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "repo.sqlite"
        self.backup = self.path.with_name("backup.sqlite")
        self.repo = Repository(self.path, initialize=True)
        self.addCleanup(self.repo.db.close)
        with self.repo.transaction(write=True):
            self.repo.put("10", "message", {"id":"100", "body":"saved"}, "src", False)
        self.repo.backup(self.backup)
        with self.repo.transaction(write=True):
            self.repo.put("10", "message", {"id":"100", "body":"current"}, "src", False)
        self.initial = self.repo.snapshot()

    @contextmanager
    def child(self, code, *args):
        with subprocess.Popen([sys.executable, "-c", code, str(self.path), *map(str, args)],
                              text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as proc:
            try:
                yield proc
            finally:
                if proc.poll() is None:
                    proc.kill()

    def read_line(self, proc):
        self.assertTrue(select.select([proc.stdout], [], [], 10)[0], "Child did not reach barrier")
        return proc.stdout.readline().strip()

    def refused(self, begin):
        before = (self.path.read_bytes(), self.repo.witness.path.read_bytes())
        with self.child(READER, begin) as proc:
            self.assertEqual(self.read_line(proc), self.initial["generation"])
            self.assertFalse(self.path.with_name(self.path.name + "-journal").exists())
            with self.assertRaises(RepositoryError):
                Repository.restore(self.path, self.backup)
            self.assertEqual((self.path.read_bytes(), self.repo.witness.path.read_bytes()), before)
            proc.stdin.write("\n")
            proc.stdin.flush()
            self.assertEqual(self.read_line(proc), self.initial["generation"])
            self.assertEqual(proc.wait(timeout=10), 0)
        self.assertEqual(self.repo.snapshot(), self.initial)

    def test_no_journal_active_reader_is_refused(self):
        self.refused("BEGIN")

    def test_no_journal_active_writer_is_refused(self):
        self.refused("BEGIN IMMEDIATE")

    def test_wal_without_sidecars_is_refused(self):
        with Repository(self.path.with_name("wal.sqlite"), initialize=True) as repo:
            backup = self.path.with_name("wal-backup.sqlite")
            repo.backup(backup)
            path, witness = repo.path, repo.witness.path
            self.assertEqual(repo.db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        self.assertFalse(path.with_name(path.name + "-wal").exists())
        self.assertFalse(path.with_name(path.name + "-shm").exists())
        before = path.read_bytes(), witness.read_bytes()
        with self.assertRaisesRegex(RepositoryError, "rollback journal mode"):
            Repository.restore(path, backup)
        self.assertEqual((path.read_bytes(), witness.read_bytes()), before)

    def test_restore_preserves_generation_boundary_and_rejects_old_handle(self):
        generation = Repository.restore(self.path, self.backup)
        self.assertNotEqual(generation, self.initial["generation"])
        for call in (self.repo.snapshot, self.repo.state, self.repo.watermark,
                     lambda: self.repo.legacy_mapping("x", "y")):
            with self.assertRaises(WitnessError):
                call()
        with self.assertRaises(WitnessError):
            with self.repo.transaction(write=True):
                self.fail("A stale Repository opened a write transaction")
        with Repository(self.path) as restored:
            self.assertTrue(restored.verify())
            self.assertEqual(restored.snapshot()["objects"][0]["data"]["body"], "saved")
            self.assertEqual(restored.changes(self.initial["generation"], self.initial["event_seq"])["mode"], "snapshot")
            with self.assertRaises(RepositoryError):
                restored.replay(self.initial["generation"], self.initial["event_seq"], 10)

    def test_contenders_are_blocked_before_and_after_atomic_swap(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase), self.child(RESTORE, self.backup, phase) as restoring:
                self.assertEqual(self.read_line(restoring), "ready")
                for begin in ("BEGIN", "BEGIN IMMEDIATE"):
                    with self.child(TRY_SQLITE, begin) as competitor:
                        out, err = competitor.communicate(timeout=10)
                        self.assertEqual(competitor.returncode, 0, err)
                        self.assertEqual(out.strip(), "busy")
                with self.assertRaisesRegex(WitnessError, "busy"):
                    Repository(self.path)
                if phase == "before":
                    with self.assertRaisesRegex(WitnessError, "busy"):
                        self.repo.snapshot()
                restoring.stdin.write("resume\n")
                restoring.stdin.flush()
                out, err = restoring.communicate(timeout=10)
                self.assertEqual(restoring.returncode, 0, err)
                with Repository(self.path) as fresh:
                    self.assertEqual(fresh.generation, out.strip())
                    self.assertTrue(fresh.verify())

    def test_restore_interruption_before_and_after_swap(self):
        with self.child(RESTORE, self.backup, "crash-before") as proc:
            self.assertEqual(proc.communicate(timeout=10)[0].strip(), "ready")
            self.assertEqual(proc.returncode, 71)
        with self.assertRaises(WitnessError):
            Repository(self.path)
        first = Repository.restore(self.path, self.backup)
        with self.child(RESTORE, self.backup, "crash-after") as proc:
            self.assertEqual(proc.communicate(timeout=10)[0].strip(), "ready")
            self.assertEqual(proc.returncode, 71)
        with Repository(self.path) as recovered:
            self.assertNotEqual(recovered.generation, first)
            self.assertIsNone(recovered.witness.read()["pending"])
            self.assertEqual(recovered.changes(self.initial["generation"], self.initial["event_seq"])["mode"], "snapshot")
            self.assertTrue(recovered.verify())
