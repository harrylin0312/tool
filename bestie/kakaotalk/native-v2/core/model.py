import hashlib
import json

MAX_ID = (1 << 63) - 1


def native_id(value):
    """Preserve SQLite signed positive native IDs as canonical decimal text."""
    if type(value) is int:
        value = str(value)
    if (not isinstance(value, str) or not value.isascii() or not value.isdecimal()
            or not 1 <= len(value) <= 19 or not 0 < int(value) <= MAX_ID
            or str(int(value)) != value):
        raise ValueError("Invalid native ID")
    return value


def optional_id(value):
    return None if value in (None, 0, "0") else native_id(value)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def object_id(room, kind, identifier):
    return kind + "_" + fingerprint([room, kind, native_id(identifier)])
