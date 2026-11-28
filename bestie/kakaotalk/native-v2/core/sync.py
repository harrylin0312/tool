"""Single-writer synchronization with a fixed upstream upper bound."""
import time

from .model import native_id
from .repository import RepositoryError


def batches(reader, after, upper, page, *, include_floor=False):
    while upper is not None:
        rows = reader.messages(after, upper, page, include_floor=include_floor)
        if not rows:
            return
        previous = int(after) if after else 0
        for row in rows:
            index = int(native_id(row["id"]))
            if index < previous or (index == previous and not include_floor) or index > int(upper):
                raise RepositoryError("Source page ordering or upper bound is invalid")
            include_floor = False
            previous = index
        yield rows
        after = rows[-1]["id"]


def run(repo, source, operation, *, page=128, overlap=100, interval=3600,
        accept_source_generation=False, clock=time.time):
    if page < 1 or overlap < 1 or interval < 1:
        raise ValueError("Synchronization limits must be positive")
    # Take the local write reservation before opening the source.
    # It excludes another CLI process even while the first is reading.
    with repo.transaction(write=True), source.open() as reader:
        state = repo.state()
        if (operation == "import") != (state is None):
            raise RepositoryError("Import requires an empty sync state, other operations require import")
        origin = getattr(reader, "origin_token", None)
        replacement = bool(state and state["source_generation"] != reader.generation)
        if state and state["origin_token"] and origin and state["origin_token"] != origin and not replacement:
            raise RepositoryError("Source file was replaced without a generation change")
        if state and (state["room"], state["link"]) != reader.identity:
            raise RepositoryError("Source room identity changed")
        if replacement and not (operation == "reconcile" and accept_source_generation):
            raise RepositoryError("Source generation changed, explicit reconciliation required")
        if state and not replacement and reader.captured_ns < state["captured_ns"]:
            raise RepositoryError("Snapshot is older than the last applied snapshot")
        upper = reader.latest()
        previous = state["high_water"] if state else None
        if previous and not replacement and (upper is None or int(upper) < int(previous)):
            raise RepositoryError("Source high-water regressed, verify source generation first")
        checked_at = clock()
        full = operation in ("import", "reconcile") or checked_at - state["reconciled_at"] >= interval
        if full:
            reader.validate_full()
        begin = None if full or not previous else reader.recent_floor(previous, overlap)
        counts = {"messages_read": 0, "changes": 0, "not_observed": 0, "full": full}
        seen = {"message": set(), "author": set(), "thread": set()}
        for kind, records in (("author", reader.authors()), ("thread", reader.threads())):
            for row in records:
                if row["id"] in seen[kind]:
                    raise RepositoryError("Duplicate author or thread identity")
                seen[kind].add(row["id"])
                counts["changes"] += repo.put(reader.room, kind, row, reader.generation, not state)
        for rows in batches(reader, begin, upper, page, include_floor=begin is not None):
            for row in rows:
                nid = row["id"]
                historical = not state or bool(previous and int(nid) <= int(previous))
                if full:
                    seen["message"].add(nid)
                counts["messages_read"] += 1
                counts["changes"] += repo.put(reader.room, "message", row, reader.generation, historical)
        if upper is not None and (full or upper != previous) and (not counts["messages_read"] or nid != upper):
            raise RepositoryError("Incomplete source batch, expected upper bound was not read")
        reader.verify()
        if full:
            counts["not_observed"] = sum(repo.note_absent(kind, ids) for kind, ids in seen.items())
        repo.save_state(*reader.identity, reader.generation, reader.captured_ns, upper,
                        checked_at if full else state["reconciled_at"],
                        origin if origin or replacement or not state else state["origin_token"])
        return counts
