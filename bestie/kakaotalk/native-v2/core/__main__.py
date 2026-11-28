"""Offline CLI. Key comes from stdin and private snapshots never go to stdout."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from .repository import Repository, RepositoryError
from .source import NativeSnapshot, SourceError, capture, seal
from .sync import run


def positive(value):
    number = int(value)
    if not 0 < number <= 100_000_000:
        raise argparse.ArgumentTypeError("expected positive integer up to 100000000")
    return number


def nonnegative(value):
    number = int(value)
    if not 0 <= number < 1 << 63:
        raise argparse.ArgumentTypeError("expected nonnegative SQLite integer")
    return number


def parser():
    root = argparse.ArgumentParser(description="KakaoTalk Reader V2 isolated local core")
    commands = root.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("seal")
    prep.add_argument("--snapshot", type=Path, required=True)
    prep.add_argument("--source-generation", required=True)
    cp = commands.add_parser("capture")
    cp.add_argument("--source-db", type=Path, required=True)
    cp.add_argument("--snapshot", type=Path, required=True)
    cp.add_argument("--source-generation", required=True)
    for command in ("init", "import", "sync", "reconcile", "status", "stats", "snapshot", "events", "verify"):
        p = commands.add_parser(command)
        p.add_argument("--repo", type=Path, required=True)
        if command in ("import", "sync", "reconcile"):
            p.add_argument("--snapshot", type=Path, required=True)
            p.add_argument("--room", required=True)
            p.add_argument("--sqlcipher", type=Path, required=True)
            p.add_argument("--page", type=positive, default=128)
            p.add_argument("--overlap", type=positive, default=100)
            p.add_argument("--reconcile-interval", type=positive, default=3600)
            if command == "reconcile":
                p.add_argument("--accept-source-generation", action="store_true")
        if command == "snapshot":
            p.add_argument("--output", required=True, type=Path)
        if command == "events":
            p.add_argument("--generation", required=True)
            p.add_argument("--after", required=True, type=nonnegative)
            p.add_argument("--limit", type=positive, default=100)
    return root


def export_snapshot(repo, output):
    value = repo.snapshot()
    # Publish only after the complete export reaches disk. link() never replaces an existing output.
    with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
        os.link(handle.name, output)
    return {"generation": value["generation"], "event_seq": value["event_seq"]}


def main():
    args = parser().parse_args()
    if args.command == "seal":
        seal(args.snapshot, args.source_generation)
        result = {"sealed": True}
    elif args.command == "capture":
        capture(args.source_db, args.snapshot, args.source_generation)
        result = {"sealed": True}
    else:
        with Repository(args.repo, initialize=args.command == "init") as repo:
            if args.command in ("import", "sync", "reconcile"):
                key = sys.stdin.buffer.readline(4097).rstrip(b"\r\n")
                if not key or len(key) > 4096:
                    raise SourceError("Expected source key on stdin")
                source = NativeSnapshot(args.snapshot, args.room, args.sqlcipher, key)
                result = run(repo, source, args.command, page=args.page, overlap=args.overlap,
                             interval=args.reconcile_interval,
                             accept_source_generation=getattr(args, "accept_source_generation", False))
            elif args.command == "events":
                result = repo.replay(args.generation, args.after, args.limit)
            elif args.command == "snapshot":
                result = export_snapshot(repo, args.output)
            elif args.command == "verify":
                result = {"ok": repo.verify()}
                if not result["ok"]:
                    raise RepositoryError("Repository integrity check failed")
            elif args.command == "status":
                state = repo.state()
                result = {"generation": repo.generation, "initialized": state is not None,
                          "snapshot_sealed_ns": state["captured_ns"] if state else None,
                          "reconciled_at": state["reconciled_at"] if state else None,
                          "event_seq": repo.watermark()}
            else:
                result = repo.statistics()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RepositoryError, SourceError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except sqlite3.Error as exc:
        print("Repository database operation failed: " + getattr(exc, "sqlite_errorname", "SQLite error"),
              file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, TypeError, KeyError):
        print("Invalid input, snapshot or local file operation failed", file=sys.stderr)
        sys.exit(1)
