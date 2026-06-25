import json
import os
from io import BytesIO
from pathlib import Path

from brain_share.config import BrainShareConfig
from brain_share.intake_server import make_app, _file_sink, _seen_ids_from_dir
from brain_share.sync_agent import SyncQueue, SyncAgent


def _wsgi_post(app, path, body):
    captured = {}
    def start(status, headers): captured["status"] = status
    env = {"REQUEST_METHOD":"POST","PATH_INFO":path,
           "CONTENT_LENGTH":str(len(body)),"wsgi.input":BytesIO(body)}
    out = b"".join(app(env, start))
    return captured["status"], out


def test_leaf_upload_to_main_blocks_sensitive_and_persists_safe(tmp_path):
    """End-to-end: sync_agent collects 3 items (1 safe, 1 sensitive division,
    1 sensitive keyword) -> flush via in-process WSGI to intake_server ->
    only the safe item lands in incoming/<node_id>/, sensitive ones rejected
    with reason='sensitive' and never touch disk."""
    cfg = BrainShareConfig(
        role="HUB", read_key="shared-key",
        blocked_divisions=["CUSTOMER"],
        blocked_keyword_patterns=["api_key"],
        allowed_collections=["knowledge","incoming"],
    )
    incoming = tmp_path / "incoming"
    sink = _file_sink(incoming)
    loader = _seen_ids_from_dir(incoming)
    app = make_app(cfg, sink, loader)

    # In-process HTTP shim — sync_agent's http_post receives (url, body),
    # we route it through the WSGI app and return (status_code:int, resp_bytes).
    def in_proc_post(url, body):
        status_str, resp = _wsgi_post(app, "/intake", body)
        return (int(status_str.split()[0]), resp)

    q = SyncQueue(str(tmp_path / "queue.db"))
    agent = SyncAgent(cfg, node_id="leafX",
                      intake_url="http://main:9212/intake",
                      queue=q, http_post=in_proc_post)
    # leafX cfg also needs read_key for auth
    agent.config = BrainShareConfig(role="LEAF", read_key="shared-key")

    agent.collect([
        {"content":"safe operational note","collection":"knowledge",
         "metadata":{"division":"TECH"}},
        {"content":"customer phone list 010-...","collection":"knowledge",
         "metadata":{"division":"CUSTOMER"}},
        {"content":"the api_key is abc","collection":"knowledge",
         "metadata":{"division":"TECH"}},
    ])
    assert q.pending_count() == 3

    out = agent.flush()
    assert out["accepted"] == 1
    assert out["rejected"] == 2
    assert q.pending_count() == 0

    # Disk check — only one file under incoming/leafX/
    files = list((incoming / "leafX").rglob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert "safe operational note" in saved["content"]
    # Sensitive content NEVER hit disk
    full = "\n".join(p.read_text(encoding="utf-8")
                     for p in incoming.rglob("*.json"))
    assert "api_key" not in full
    assert "010-" not in full


def test_repeat_flush_is_idempotent(tmp_path):
    cfg = BrainShareConfig(role="HUB", read_key="k",
                           allowed_collections=["knowledge","incoming"])
    incoming = tmp_path / "incoming"
    sink = _file_sink(incoming)
    loader = _seen_ids_from_dir(incoming)
    app = make_app(cfg, sink, loader)
    def post(url, body):
        s, r = _wsgi_post(app, "/intake", body)
        return (int(s.split()[0]), r)

    q = SyncQueue(str(tmp_path/"q.db"))
    agent = SyncAgent(cfg, node_id="leafY",
                      intake_url="http://x/intake", queue=q, http_post=post)
    agent.config = BrainShareConfig(role="LEAF", read_key="k")
    agent.collect([{"content":"hello world","collection":"knowledge"}])
    agent.flush()
    # Re-collect same content, re-flush — must dedupe everywhere
    agent.collect([{"content":"hello world","collection":"knowledge"}])
    out = agent.flush()
    # Either nothing pending (queue dedupe) or server rejects as duplicate
    files = list(incoming.rglob("*.json"))
    assert len(files) == 1
