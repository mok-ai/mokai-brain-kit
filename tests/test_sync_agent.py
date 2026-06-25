import json
import sqlite3
import pytest
from brain_share.config import BrainShareConfig
from brain_share.sync_agent import SyncQueue, SyncAgent


def cfg():
    return BrainShareConfig(role="LEAF", read_key="k")


def items(*texts):
    return [{"content": t, "collection": "knowledge",
             "metadata": {"division": "TECH"}} for t in texts]


def test_queue_enqueue_assigns_ids_and_dedupes(tmp_path):
    q = SyncQueue(str(tmp_path / "q.db"))
    a = q.enqueue([{"id":"a","content":"x"},{"id":"b","content":"y"}])
    b = q.enqueue([{"id":"a","content":"x"},{"id":"c","content":"z"}])  # 'a' is dup
    assert a == 2
    assert b == 1
    assert q.pending_count() == 3


def test_queue_pending_then_mark_sent(tmp_path):
    q = SyncQueue(str(tmp_path / "q.db"))
    q.enqueue([{"id":"a","content":"x"},{"id":"b","content":"y"}])
    pend = q.pending()
    assert {p["id"] for p in pend} == {"a","b"}
    q.mark_sent(["a"])
    assert {p["id"] for p in q.pending()} == {"b"}


def test_agent_collect_assigns_node_scoped_id_and_dedupes(tmp_path):
    q = SyncQueue(str(tmp_path / "q.db"))
    a = SyncAgent(cfg(), node_id="leaf1", intake_url="http://x/intake",
                  queue=q, http_post=lambda url, body: (200, b'{"accepted":[],"rejected":[]}'))
    n1 = a.collect([{"content":"hello","collection":"knowledge"}])
    n2 = a.collect([{"content":"hello","collection":"knowledge"}])  # same content -> dup
    assert (n1, n2) == (1, 0)
    assert q.pending_count() == 1


def test_agent_flush_marks_accepted_and_keeps_transient(tmp_path):
    q = SyncQueue(str(tmp_path / "q.db"))
    sent = []
    def fake_post(url, body):
        data = json.loads(body)
        sent.append([i["id"] for i in data["items"]])
        # accept first, reject second as duplicate (still mark_sent — server knows)
        ids = [i["id"] for i in data["items"]]
        return (200, json.dumps({
            "accepted":[ids[0]] if ids else [],
            "rejected":[{"id": ids[1], "reason":"duplicate"}] if len(ids) > 1 else []
        }).encode())
    a = SyncAgent(cfg(), "leaf1", "http://x/intake", q, http_post=fake_post)
    a.collect([{"content":"a"},{"content":"b"}])
    out = a.flush()
    assert out["sent"] == 2
    assert out["accepted"] == 1
    assert out["rejected"] == 1
    assert q.pending_count() == 0  # both removed (server saw them)


def test_agent_flush_keeps_queue_on_network_error(tmp_path):
    q = SyncQueue(str(tmp_path / "q.db"))
    def fail_post(url, body):
        raise ConnectionError("main down")
    a = SyncAgent(cfg(), "leaf1", "http://x/intake", q, http_post=fail_post)
    a.collect([{"content":"a"}])
    out = a.flush()
    assert out.get("error") == "network"
    assert q.pending_count() == 1  # preserved for catchup


def test_agent_catchup_sends_backlog(tmp_path):
    q = SyncQueue(str(tmp_path / "q.db"))
    q.enqueue([{"id":"x1","content":"backlog"}])  # pre-existing from last shutdown
    posted = []
    def post(url, body):
        posted.append(json.loads(body)["items"])
        return (200, b'{"accepted":["x1"],"rejected":[]}')
    a = SyncAgent(cfg(), "leaf1", "http://x/intake", q, http_post=post)
    a.catchup()
    assert posted == [[{"id":"x1","content":"backlog"}]]
    assert q.pending_count() == 0


def test_agent_does_not_import_heavy_modules():
    """sync_agent must stay light: no numpy/chromadb/sentence_transformers."""
    import brain_share.sync_agent as m
    src = open(m.__file__, "r", encoding="utf-8").read()
    for forbidden in ("import numpy", "import chromadb", "import sentence_transformers"):
        assert forbidden not in src, f"sync_agent must not import {forbidden}"
