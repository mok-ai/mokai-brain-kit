"""Pure validation gate for items uploaded from leaf agents.

This is the LAST defense against sensitive-data leakage in the auto-merge
pipeline: every incoming item passes through validate_incoming() before
being written to disk or indexed.  Therefore the implementation MUST stay
pure (no IO, no side effects) and decisively reject anything dubious.
"""
import hashlib

from brain_share.config import BrainShareConfig
from brain_share.sensitivity_filter import is_blocked


def compute_item_id(node_id: str, content: str) -> str:
    """Deterministic 16-char hex id, scoped to (node_id, content)."""
    h = hashlib.sha256()
    h.update(node_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(content.encode("utf-8"))
    return h.hexdigest()[:16]


def validate_incoming(item: dict, config: BrainShareConfig,
                      seen_ids: set) -> tuple:
    """Return (ok: bool, reason: str). Reason in
    {ok, sensitive, duplicate, empty, missing_id}."""
    item_id = item.get("id")
    if not item_id:
        return (False, "missing_id")
    if item_id in seen_ids:
        return (False, "duplicate")
    content = str(item.get("content", "") or "")
    if not content.strip():
        return (False, "empty")
    # Sensitivity is last so leakage attempts always show 'sensitive' in logs.
    if is_blocked(item, config):
        return (False, "sensitive")
    return (True, "ok")
