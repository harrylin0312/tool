"""Offline CLI. Key comes from stdin and private snapshots never go to stdout."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from .authority import bind, trusted_capture
from .batch import page
from .witness import WitnessError
from .repository import Repository, RepositoryError
from .source import NativeSnapshot, SourceError, seal
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
    pg = commands.add_parser("page")
    pg.add_argument("--batch", type=Path, required=True)
    pg.add_argument("--offset", type=nonnegative, default=0)
    pg.add_argument("--limit", type=positive, default=100)
    pg.add_argument("--output", type=Path, required=True)
    names = ("init", "adopt", "bind-source", "capture", "import", "sync", "reconcile",
             "status", "stats", "snapshot", "events", "verify", "backup", "restore", "changes")
    for command in names:
        p = commands.add_parser(command)
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--witness", type=Path)
        if command in ("bind-source", "capture"):
            p.add_argument("--source-db", type=Path, required=True)
            p.add_argument("--source-generation", required=True)
            if command == "capture":
                p.add_argument("--snapshot", type=Path, required=True)
            else:
                p.add_argument("--replace-binding", action="store_true")
        if command in ("import", "sync", "reconcile"):
            p.add_argument("--snapshot", type=Path, required=True)
            p.add_argument("--room", required=True)
            p.add_argument("--sqlcipher", type=Path, required=True)
            p.add_argument("--page", type=positive, default=128)
            p.add_argument("--overlap", type=positive, default=100)
            p.add_argument("--reconcile-interval", type=positive, default=3600)
            if command == "reconcile":
                p.add_argument("--accept-source-generation", action="store_true")
                p.add_argument("--recover-external", action="store_true")
        if command in ("snapshot", "changes", "backup"):
            p.add_argument("--output", required=True, type=Path)
        if command in ("events", "changes"):
            p.add_argument("--generation", required=True)
            p.add_argument("--after", required=True, type=nonnegative)
        if command == "events":
            p.add_argument("--limit", type=positive, default=100)
        if command == "restore":
            p.add_argument("--backup", type=Path, required=True)
    return root


def write_private(value, output):
    # Publish only after the complete export reaches disk. link() never replaces an existing output.
    with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
        os.link(handle.name, output)



def main():
    args = parser().parse_args()
    if args.command == "seal":
        seal(args.snapshot, args.source_generation)
        result = {"sealed": True}
    elif args.command == "page":
        with args.batch.open() as handle:
            result_page = page(json.load(handle), args.offset, args.limit)
        write_private(result_page, args.output)
        result = {"batch_id": result_page["batch_id"], "next_offset": result_page["next_offset"]}
    elif args.command == "restore":
        result = {"generation": Repository.restore(args.repo, args.backup, witness=args.witness)}

    else:
        with Repository(args.repo, initialize=args.command == "init", witness=args.witness,
                        adopt=args.command == "adopt") as repo:
            if args.command in ("import", "sync", "reconcile"):
                key = sys.stdin.buffer.readline(4097).rstrip(b"\r\n")
                if not key or len(key) > 4096:
                    raise SourceError("Expected source key on stdin")
                source = NativeSnapshot(args.snapshot, args.room, args.sqlcipher, key)
                result = run(repo, source, args.command, page=args.page, overlap=args.overlap,
                             interval=args.reconcile_interval,
                             accept_source_generation=getattr(args, "accept_source_generation", False),
                             recover_external=getattr(args, "recover_external", False))
            elif args.command == "events":
                result = repo.replay(args.generation, args.after, args.limit)
            elif args.command == "snapshot":
                view = repo.snapshot()
                write_private(view, args.output)
                result = {"generation": view["generation"], "event_seq": view["event_seq"]}
            elif args.command == "changes":
                batch = repo.changes(args.generation, args.after)
                write_private(batch, args.output)
                result = {key: batch[key] for key in ("batch_id", "generation", "start", "end", "mode")}
            elif args.command == "backup":
                repo.backup(args.output)
                result = {"backup": True}
            elif args.command == "bind-source":
                bind(repo, args.source_db, args.source_generation, replace=args.replace_binding)
                result = {"bound": True}
            elif args.command == "capture":
                trusted_capture(repo, args.source_db, args.snapshot, args.source_generation)
                result = {"sealed": True, "trusted": True}
            elif args.command == "verify":
                result = {"ok": repo.verify()}
                if not result["ok"]:
                    raise RepositoryError("Repository integrity check failed")
            elif args.command == "status":
                with repo.transaction():
                    state = repo.state()
                    result = {"generation": repo.generation, "initialized": state is not None,
                              "snapshot_sealed_ns": state["captured_ns"] if state else None,
                              "source_trust": ("bound_capture" if state["source_counter"] is not None
                                               else "external_copy") if state else None,
                              "reconciled_at": state["reconciled_at"] if state else None,
                              "event_seq": repo.watermark()}
            else:
                result = repo.statistics()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RepositoryError, SourceError, WitnessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except sqlite3.Error as exc:
        print("Repository database operation failed: " + getattr(exc, "sqlite_errorname", "SQLite error"),
              file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, TypeError, KeyError):
        print("Invalid input, snapshot or local file operation failed", file=sys.stderr)
        sys.exit(1)
