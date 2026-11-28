"""Authorize ordered local captures from an explicitly bound source."""
import hashlib
import hmac
from pathlib import Path
import secrets

from .model import encode, fingerprint
from .source import SourceError, capture


def origin(path):
    info = path.stat()
    return hashlib.sha256(repr((info.st_dev, info.st_ino)).encode()).hexdigest()


def mac(secret, manifest, counter):
    payload = {k: v for k, v in manifest.items() if k != "receipt"}
    return hmac.new(bytes.fromhex(secret), encode([payload, counter]).encode(), "sha256").hexdigest()


def bind(repo, source, generation, *, replace=False):
    source = Path(source).resolve(strict=True)
    if not generation.strip() or not source.is_file():
        raise SourceError("Binding requires an existing regular source and a generation")
    with repo.transaction(write=True):
        record = repo.witness_record
        prior = record.get("capture")
        previous_generation = repo.state()
        if prior and prior["path"] == str(source) and prior["generation"] == generation and prior["origin"] == origin(source):
            return
        if prior and (not replace or prior["generation"] == generation):
            raise SourceError("Explicit new generation required to replace capture binding")
        if previous_generation and prior and previous_generation["source_generation"] == generation:
            raise SourceError("Capture replacement requires a new generation")
        record["capture"] = {
            "path": str(source), "generation": generation, "origin": origin(source),
            "secret": secrets.token_hex(32), "counter": 0,
        }
        repo.witness.write(record)


def trusted_capture(repo, source, destination, generation):
    source = Path(source).resolve(strict=True)
    with repo.transaction(write=True):
        record = repo.witness_record
        binding = record.get("capture")
        if not binding or binding["path"] != str(source) or binding["generation"] != generation:
            raise SourceError("Capture source is not bound to this repository")
        if origin(source) != binding["origin"]:
            raise SourceError("Bound capture origin was replaced; bind a new generation")
        counter = binding["counter"] + 1
        # Reserve the number before making the receipt visible. Failed captures leave a safe gap.
        binding["counter"] = counter
        repo.witness.write(record)

        def sign(manifest):
            if manifest["origin_token"] != binding["origin"] or origin(source) != binding["origin"]:
                raise SourceError("Bound capture origin changed during capture")
            return {"counter": counter, "mac": mac(binding["secret"], manifest, counter)}

        capture(source, destination, generation, sign=sign)


def authenticate(repo, manifest):
    receipt = manifest.get("receipt")
    if receipt is None:
        return None, None
    binding = repo.witness_record.get("capture")
    if (not isinstance(receipt, dict) or type(receipt.get("counter")) is not int
            or not isinstance(receipt.get("mac"), str) or not binding):
        raise SourceError("Invalid trusted capture receipt")
    counter = receipt["counter"]
    if (binding["generation"] != manifest["generation"] or binding["origin"] != manifest["origin_token"]
            or not 0 < counter == binding["counter"]
            or not hmac.compare_digest(receipt["mac"], mac(binding["secret"], manifest, counter))):
        raise SourceError("Capture receipt does not match the bound source")
    return counter, fingerprint(manifest)
