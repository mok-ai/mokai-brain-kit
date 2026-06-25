"""Main-brain canonicalization daemon (periodic, incremental).

Walks incoming/<node_id>/*.json, groups by topic, and for each topic with
new items since the last watermark, calls wiki_synth.synthesize_topic to
produce a canonical wiki page in the vault.

Heavy deps (claude llm, embedding extractor, chroma indexer) are INJECTED
so unit tests run without them.
"""
import json
import logging
import sqlite3
import time
from pathlib import Path

from brain_share.wiki_synth import synthesize_topic
from brain_share.wiki_store import WikiStore

log = logging.getLogger("brain_share.synth")


class SynthWatermark:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._c = sqlite3.connect(db_path, isolation_level=None,
                                  check_same_thread=False)
        self._c.execute("""CREATE TABLE IF NOT EXISTS watermark(
            topic TEXT PRIMARY KEY, latest_id TEXT NOT NULL, updated_at REAL)""")

    def last_seen(self, topic: str):
        r = self._c.execute("SELECT latest_id FROM watermark WHERE topic=?",
                            (topic,)).fetchone()
        return r[0] if r else None

    def record(self, topic: str, latest_id: str):
        self._c.execute(
            "INSERT OR REPLACE INTO watermark(topic, latest_id, updated_at) VALUES (?,?,?)",
            (topic, latest_id, time.time()))


def _default_topic(item: dict) -> str:
    meta = item.get("metadata") or {}
    return str(meta.get("topic") or "general")


def discover_topics(incoming_dir, topic_fn=None) -> dict:
    incoming_dir = Path(incoming_dir)
    topic_fn = topic_fn or _default_topic
    groups: dict = {}
    if not incoming_dir.exists():
        return groups
    for p in sorted(incoming_dir.rglob("*.json")):
        try:
            item = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        groups.setdefault(topic_fn(item), []).append(item)
    return groups


class _NoopIndexer:
    def upsert(self, *, id, text, metadata): pass
    def search(self, query, top_k): return []


def synth_once(incoming_dir, vault_dir: str, watermark: SynthWatermark,
               llm_fn, extractor_fn, indexer=None,
               updated: str = "auto", topic_fn=None) -> dict:
    groups = discover_topics(incoming_dir, topic_fn=topic_fn)
    if updated == "auto":
        updated = time.strftime("%Y-%m-%d")
    store = WikiStore(vault_dir, indexer or _NoopIndexer())
    topics_synthed = 0
    items_seen = 0
    skipped = 0
    for topic, items in groups.items():
        items_seen += len(items)
        # 'latest' = max item id in deterministic order (sorted ids)
        latest = max(i["id"] for i in items)
        if watermark.last_seen(topic) == latest:
            skipped += 1
            continue
        page = synthesize_topic(topic=topic, namespace="incoming",
                                chunks=items, updated=updated,
                                llm_fn=llm_fn, extractor_fn=extractor_fn)
        written_path = store.upsert(page)
        if not written_path:
            log.warning("synth: empty body for topic=%s, skipping watermark (will retry)", topic)
            skipped += 1
            continue
        watermark.record(topic, latest)
        topics_synthed += 1
    log.info("synth pass topics=%d items=%d skipped=%d",
             topics_synthed, items_seen, skipped)
    return {"topics_synthed": topics_synthed,
            "items_seen": items_seen, "skipped": skipped}


def run_daemon(incoming_dir, vault_dir: str, watermark_db: str,
               llm_fn, extractor_fn, period_seconds: int = 300,
               indexer=None):
    logging.basicConfig(filename="synth_daemon.log", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    wm = SynthWatermark(watermark_db)
    while True:
        try:
            synth_once(incoming_dir, vault_dir, wm, llm_fn, extractor_fn,
                       indexer=indexer)
        except Exception as e:
            log.warning("synth pass error: %s", e)
        time.sleep(period_seconds)
