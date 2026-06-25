"""Main brain intake server (:9212).

Receives uploaded items from leaf agents, runs them through intake_filter,
and persists accepted items to incoming/<node_id>/ + optional RAG index.

LAST DEFENSE: every item passes intake_filter.validate_incoming before
hitting disk.  No bypass paths.
"""
import hmac
import json
import logging
import os
import re
from pathlib import Path
from wsgiref.simple_server import make_server

from brain_share.config import BrainShareConfig, load_config
from brain_share.intake_filter import validate_incoming

log = logging.getLogger("brain_share.intake")

# Security: regex patterns for path-traversal prevention
_NODE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_ITEM_ID_RE = re.compile(r"[A-Za-z0-9]{1,64}")


def process_batch(node_id: str, items: list, config: BrainShareConfig,
                  seen_ids: set, sink_fn) -> dict:
    """Apply intake_filter to each item; call sink_fn(node_id, item) for
    accepted items only.  Returns {accepted:[ids], rejected:[{id,reason}]}.
    Rejects items with invalid id format (path-traversal guard)."""
    accepted = []
    rejected = []
    # Mutate a copy so the caller's seen_ids stays untouched until persistence.
    local_seen = set(seen_ids)
    for item in items:
        # Path-traversal guard: reject item if id is malformed
        item_id = item.get("id", "")
        if item_id and not _ITEM_ID_RE.fullmatch(item_id):
            rejected.append({"id": item_id, "reason": "invalid_id"})
            continue

        ok, reason = validate_incoming(item, config, local_seen)
        if ok:
            sink_fn(node_id, item)
            accepted.append(item["id"])
            local_seen.add(item["id"])
        else:
            rejected.append({"id": item.get("id", "<missing>"), "reason": reason})
    return {"accepted": accepted, "rejected": rejected}


def make_app(config: BrainShareConfig, sink_fn, seen_ids_loader):
    """Return a WSGI app implementing POST /intake."""
    expected_key = (config.read_key or "").encode("utf-8")

    def app(environ, start_response):
        if environ.get("REQUEST_METHOD") != "POST" \
           or environ.get("PATH_INFO") != "/intake":
            start_response("404 Not Found", [("Content-Type","text/plain")])
            return [b"not found"]
        try:
            n = int(environ.get("CONTENT_LENGTH") or 0)
            body = environ["wsgi.input"].read(n) if n > 0 else b""
            data = json.loads(body.decode("utf-8"))
        except Exception:
            start_response("400 Bad Request", [("Content-Type","text/plain")])
            return [b"bad json"]
        node_id = data.get("node_id", "")
        key = (data.get("key", "") or "").encode("utf-8")
        items = data.get("items", []) or []

        # Path-traversal guard: reject malformed or empty node_id (empty would
        # land items at incoming/<id>.json instead of incoming/<node>/<id>.json,
        # breaking per-leaf isolation).
        if not node_id or not _NODE_ID_RE.fullmatch(node_id):
            log.warning("invalid node_id rejected=%s", node_id)
            start_response("400 Bad Request", [("Content-Type","text/plain")])
            return [b'{"error":"invalid node_id"}']

        if not hmac.compare_digest(key, expected_key):
            log.warning("auth fail node=%s", node_id)
            start_response("401 Unauthorized", [("Content-Type","text/plain")])
            return [b"unauthorized"]
        out = process_batch(node_id, items, config, seen_ids_loader(),
                            sink_fn)
        log.info("intake node=%s accepted=%d rejected=%d",
                 node_id, len(out["accepted"]), len(out["rejected"]))
        body_out = json.dumps(out, ensure_ascii=False).encode("utf-8")
        start_response("200 OK", [("Content-Type","application/json; charset=utf-8"),
                                  ("Content-Length", str(len(body_out)))])
        return [body_out]
    return app


def _file_sink(incoming_dir: Path, indexer=None):
    incoming_dir = Path(incoming_dir)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    def sink(node_id: str, item: dict):
        node_dir = incoming_dir / node_id
        node_dir.mkdir(parents=True, exist_ok=True)
        # Filename = item id; JSON body includes original metadata.
        (node_dir / f"{item['id']}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        if indexer is not None:
            try:
                indexer(item, node_id)
            except Exception as e:
                log.warning("indexer failed item=%s err=%s", item.get("id"), e)
    return sink


def _seen_ids_from_dir(incoming_dir: Path):
    incoming_dir = Path(incoming_dir)
    def loader():
        if not incoming_dir.exists():
            return set()
        return {p.stem for p in incoming_dir.rglob("*.json")}
    return loader


def run_server(config_path: str, incoming_dir: str, indexer=None,
               host: str = None, port: int = None):
    logging.basicConfig(filename="intake.log", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    cfg = load_config(config_path)
    bind_host = host or os.environ.get("BRAIN_SHARE_INTAKE_HOST", "127.0.0.1")
    bind_port = port or int(os.environ.get("BRAIN_SHARE_INTAKE_PORT", "9212"))
    sink = _file_sink(Path(incoming_dir), indexer=indexer)
    loader = _seen_ids_from_dir(Path(incoming_dir))
    app = make_app(cfg, sink, loader)
    srv = make_server(bind_host, bind_port, app)
    print(f"intake_server listening on {bind_host}:{bind_port}")
    srv.serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--incoming", required=True, help="incoming/ directory root")
    args = ap.parse_args()
    run_server(args.config, args.incoming)
