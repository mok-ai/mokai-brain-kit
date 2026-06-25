"""Leaf-side resident sync agent (lightweight, no LLM, stdlib only).

Polls a source iterator for new memories, enqueues them locally (SQLite),
and POSTs pending batches to the main brain intake server.

Idempotent: item.id = sha256(node_id + content)[:16] -> same content from
the same node always produces the same id, so re-enqueue/re-flush is a
no-op on the server (deduped) and locally (UNIQUE constraint).
"""
import json
import logging
import sqlite3
import time
import urllib.request
from typing import Iterable

from brain_share.config import BrainShareConfig
from brain_share.intake_filter import compute_item_id

log = logging.getLogger("brain_share.sync")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    enqueued_at REAL NOT NULL
);
"""


class SyncQueue:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, isolation_level=None,
                                     check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)

    def enqueue(self, items: list) -> int:
        added = 0
        for it in items:
            if "id" not in it:
                continue
            try:
                self._conn.execute(
                    "INSERT INTO pending(id, payload, enqueued_at) VALUES (?, ?, ?)",
                    (it["id"], json.dumps(it, ensure_ascii=False), time.time()))
                added += 1
            except sqlite3.IntegrityError:
                pass
        return added

    def pending(self, limit: int = 200) -> list:
        cur = self._conn.execute(
            "SELECT payload FROM pending ORDER BY enqueued_at LIMIT ?", (limit,))
        return [json.loads(r[0]) for r in cur.fetchall()]

    def pending_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM pending")
        return cur.fetchone()[0]

    def mark_sent(self, ids: list) -> None:
        if not ids:
            return
        self._conn.executemany("DELETE FROM pending WHERE id=?",
                               [(i,) for i in ids])


def _default_post(url: str, body: bytes):
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return (r.status, r.read())


class SyncAgent:
    def __init__(self, config: BrainShareConfig, node_id: str,
                 intake_url: str, queue: SyncQueue, http_post=None):
        self.config = config
        self.node_id = node_id
        self.intake_url = intake_url
        self.queue = queue
        self._post = http_post or _default_post

    def collect(self, source_iter: Iterable) -> int:
        """Read raw memory items, assign deterministic ids, enqueue."""
        prepared = []
        for raw in source_iter:
            content = str(raw.get("content", "") or "")
            if not content.strip():
                continue
            item = dict(raw)
            item["id"] = compute_item_id(self.node_id, content)
            prepared.append(item)
        return self.queue.enqueue(prepared)

    def flush(self) -> dict:
        items = self.queue.pending()
        if not items:
            return {"sent": 0, "accepted": 0, "rejected": 0}
        body = json.dumps({
            "node_id": self.node_id,
            "key": self.config.read_key,
            "items": items,
        }, ensure_ascii=False).encode("utf-8")
        try:
            status, resp = self._post(self.intake_url, body)
        except Exception as e:
            log.warning("flush network error: %s", e)
            return {"sent": 0, "error": "network"}
        if status != 200:
            log.warning("flush non-200: %s", status)
            return {"sent": 0, "error": f"http_{status}"}
        try:
            data = json.loads(resp.decode("utf-8"))
        except Exception:
            return {"sent": 0, "error": "bad_response"}
        seen_ids = list(data.get("accepted", [])) + \
                   [r["id"] for r in data.get("rejected", []) if "id" in r]
        self.queue.mark_sent(seen_ids)
        return {"sent": len(items),
                "accepted": len(data.get("accepted", [])),
                "rejected": len(data.get("rejected", []))}

    def catchup(self) -> dict:
        return self.flush()

    def run_forever(self, period_seconds: int = 180,
                    source_iter_factory=None):
        self.catchup()
        while True:
            if source_iter_factory is not None:
                try:
                    self.collect(source_iter_factory())
                except Exception as e:
                    log.warning("collect error: %s", e)
            try:
                self.flush()
            except Exception as e:
                log.warning("flush error: %s", e)
            time.sleep(period_seconds)
