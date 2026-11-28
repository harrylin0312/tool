"""Page a locally materialized batch without reading a moving repository."""
from .model import fingerprint
from .repository import RepositoryError


def page(batch, offset, limit):
    core = {key: value for key, value in batch.items() if key != "batch_id"}
    if batch.get("schema_version") != 2 or batch.get("batch_id") != fingerprint(core):
        raise RepositoryError("Invalid materialized change batch")
    records = batch["records"]
    if type(offset) is not int or type(limit) is not int or not 0 <= offset <= len(records) or limit < 1:
        raise RepositoryError("Invalid batch page")
    end = min(len(records), offset + limit)
    return {**{k: v for k, v in batch.items() if k != "records"},
            "offset": offset, "length": len(records), "records": records[offset:end],
            "next_offset": end if end < len(records) else None}
