"""Leaf-side resident sync agent (lightweight, no LLM, stdlib only).

Polls a source iterator for new memories, enqueues them locally (SQLite),
and POSTs pending batches to the main brain intake server.

Idempotent: item.id = sha256(node_id + content)[:16] -> same content from
the same node always produces the same id, so re-enqueue/re-flush is a
no-op on the server (deduped) and locally (UNIQUE constraint).

CLI (outbox mode)::

    python -m brain_share.sync_agent --config <ROOT>/brain_share_config.json \
        --node leaf1 --intake http://main:9212/intake

Drop item files into ``<ROOT>/outbox/*.json`` (one dict or a list of dicts,
each with a non-empty "content"). Parsed files move to ``outbox/sent/``.
Items without "collection" get the default ("knowledge") injected — the HUB
intake filter rejects any collection outside its allowed_collections as
"sensitive". Division must live in ``metadata.division`` (top-level ignored).
"""
import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
from typing import Iterable

from brain_share.config import BrainShareConfig, load_config
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


def iter_outbox(outbox_dir: str, sent_dir: str,
                default_collection: str = "knowledge"):
    """Yield items from ``outbox_dir/*.json``; move parsed files to sent_dir.

    Each file holds one dict or a list of dicts. Items missing "collection"
    get ``default_collection`` injected (the HUB intake filter rejects items
    whose collection is not in its allowed_collections as "sensitive").
    Malformed files stay in place (retried next cycle) with a warning —
    never silently discarded.
    """
    os.makedirs(sent_dir, exist_ok=True)
    for name in sorted(os.listdir(outbox_dir)):
        path = os.path.join(outbox_dir, name)
        if not name.lower().endswith(".json") or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            log.warning("outbox skip %s: %s", name, e)
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                item.setdefault("collection", default_collection)
                yield item
        shutil.move(path, os.path.join(sent_dir, name))


def main(argv=None, http_post=None):
    """CLI entry: ``python -m brain_share.sync_agent`` (LEAF_REGISTRATION 4단계).

    Watches <ROOT>/outbox for item files and uploads them to the main brain.
    ROOT is derived from --config's directory unless --outbox/--queue given.
    """
    # pythonw는 stdout이 None, 콘솔은 cp949 — 어느 쪽에서도 죽지 않게
    for _s in (sys.stdout, sys.stderr):
        try:
            if _s is not None and hasattr(_s, "reconfigure"):
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="brain_share.sync_agent",
        description="Leaf outbox uploader — <ROOT>/outbox/*.json to main intake")
    ap.add_argument("--config", required=True,
                    help="brain_share_config.json path (parent dir = ROOT)")
    ap.add_argument("--node", default=os.environ.get("AGENT_NAME"),
                    help="node id (default: $AGENT_NAME)")
    ap.add_argument("--intake", default=os.environ.get("BRAIN_INTAKE_URL"),
                    help="main intake URL (default: $BRAIN_INTAKE_URL)")
    ap.add_argument("--outbox", default=None,
                    help="outbox dir (default: <ROOT>/outbox)")
    ap.add_argument("--queue", default=None,
                    help="queue db path (default: <ROOT>/sync_queue.db)")
    ap.add_argument("--collection", default="knowledge",
                    help="collection injected when an item has none")
    ap.add_argument("--period", type=int, default=180,
                    help="flush period seconds (default 180)")
    ap.add_argument("--once", action="store_true",
                    help="single collect+flush pass, then exit")
    args = ap.parse_args(argv)
    if not args.node:
        ap.error("--node required (or set AGENT_NAME)")
    if not args.intake:
        ap.error("--intake required (or set BRAIN_INTAKE_URL)")

    cfg = load_config(args.config)
    root = os.path.dirname(os.path.abspath(args.config))
    outbox = args.outbox or os.path.join(root, "outbox")
    sent = os.path.join(outbox, "sent")
    os.makedirs(outbox, exist_ok=True)
    queue = SyncQueue(args.queue or os.path.join(root, "sync_queue.db"))
    agent = SyncAgent(cfg, node_id=args.node, intake_url=args.intake,
                      queue=queue, http_post=http_post)

    def source():
        return iter_outbox(outbox, sent, default_collection=args.collection)

    if args.once:
        agent.collect(source())
        return agent.flush()
    agent.run_forever(period_seconds=args.period, source_iter_factory=source)


if __name__ == "__main__":
    main()
