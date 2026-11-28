"""Private rollback witness, kept outside the SQLite backup set."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


class WitnessError(RuntimeError):
    pass


class Witness:
    def __init__(self, path):
        self.path = Path(path).absolute()
        if "com.kakao.KakaoTalkMac" in self.path.resolve().parts:
            raise WitnessError("Witness must be outside the KakaoTalk container")
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def locked(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            if st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
                raise WitnessError("Witness lock must be private")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WitnessError("Repository witness is busy") from None
            yield
        finally:
            os.close(fd)

    def read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(fd) as handle:
            st = os.fstat(handle.fileno())
            if st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
                raise WitnessError("Witness must be private")
            try:
                obj = json.load(handle)
                if obj.get("format") != 1:
                    raise ValueError
                return obj
            except (TypeError, ValueError, AttributeError):
                raise WitnessError("Invalid external witness") from None

    def write(self, obj):
        # Temporary file is in the same directory so the replacement is atomic.
        fd, path = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(obj, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(path, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def verify(self, actual):
        record = self.read()
        if record is None:
            raise WitnessError("Missing external witness; use explicit adoption or restore")
        pending = record.get("pending")
        if pending is not None and actual == pending:
            record["committed"] = pending
            record["pending"] = None
            self.write(record)
        elif pending is not None or actual != record.get("committed"):
            raise WitnessError("Repository history differs from witness; explicit restore required")
        return record
