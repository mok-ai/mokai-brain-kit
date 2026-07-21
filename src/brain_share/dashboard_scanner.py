# brain_share/dashboard_scanner.py
"""Pure data-collection helpers for brain_dashboard.

Every function is read-only, tolerant of missing sources (returns empty
structure rather than raising), and free of third-party deps. The
dashboard HTTP server calls collect_all() and serves the resulting dict
as JSON.
"""
import datetime
import json
import socket
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Optional


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(
        timespec="seconds")


# ─────────────────────────── scan_incoming ───────────────────────────

def scan_incoming(incoming_dir) -> dict:
    incoming_dir = Path(incoming_dir)
    empty = {"total_items": 0, "total_size_bytes": 0, "nodes": {}}
    if not incoming_dir.exists():
        return empty
    nodes = {}
    total_items = 0
    total_size = 0
    try:
        node_dirs = sorted(p for p in incoming_dir.iterdir() if p.is_dir())
    except OSError:
        return empty
    for node_dir in node_dirs:
        # Per-node-dir guard: a bad/vanished dir must not abort the whole scan.
        try:
            items = list(node_dir.glob("*.json"))
        except OSError:
            continue
        size_sum = 0
        max_mtime = None
        count = 0
        for p in items:
            # incoming/ is a live multi-writer sync target — a file can be
            # deleted between glob() and stat() (TOCTOU). Single stat() per
            # file, skip files that vanish/error rather than raising.
            try:
                st = p.stat()
            except OSError:
                continue
            size_sum += st.st_size
            count += 1
            if max_mtime is None or st.st_mtime > max_mtime:
                max_mtime = st.st_mtime
        if count == 0:
            continue
        last = datetime.datetime.fromtimestamp(
            max_mtime, datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
        nodes[node_dir.name] = {
            "items": count,
            "size_bytes": size_sum,
            "last_ts": last,
        }
        total_items += count
        total_size += size_sum
    return {"total_items": total_items, "total_size_bytes": total_size, "nodes": nodes}


# ─────────────────────────── scan_backups ────────────────────────────

def scan_backups(backups_dir) -> list:
    backups_dir = Path(backups_dir)
    if not backups_dir.exists():
        return []
    out = []
    for d in backups_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            datetime.date.fromisoformat(d.name)
        except ValueError:
            continue
        mfp = d / "manifest.json"
        if not mfp.exists():
            continue
        try:
            m = json.loads(mfp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(m, dict):
            continue
        # Schema guard: a manifest can be valid JSON but the wrong shape
        # (e.g. "files" is a list, or an entry is a string not a dict).
        # Skip the whole backup rather than let .get()/.items() raise.
        files = m.get("files", {}) or {}
        if not isinstance(files, dict):
            continue
        sha_prefixes = {}
        size_bytes = 0
        malformed = False
        for name, info in files.items():
            if not isinstance(info, dict):
                malformed = True
                break
            sha_prefixes[name] = (info.get("sha256") or "")[:8]
            size_bytes += info.get("size", 0) or 0
        if malformed:
            continue
        out.append({
            "date": m.get("date", d.name),
            "size_bytes": size_bytes,
            "sha_prefixes": sha_prefixes,
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


# ────────────────────────── scan_synth_watermark ─────────────────────

def scan_synth_watermark(watermark_db) -> dict:
    watermark_db = Path(watermark_db)
    empty = {"topics": [], "count": 0}
    if not watermark_db.exists():
        return empty
    try:
        conn = sqlite3.connect(f"file:{watermark_db}?mode=ro", uri=True)
        cur = conn.execute("SELECT topic, latest_id, updated_at FROM watermark")
        topics = [{"topic": t, "latest_id": lid, "updated_at": ua}
                  for t, lid, ua in cur.fetchall()]
        conn.close()
    except Exception:
        return empty
    return {"topics": topics, "count": len(topics)}


# ─────────────────────────── scan_graph ──────────────────────────────

def scan_graph(graph_db_path) -> dict:
    graph_db_path = Path(graph_db_path)
    empty = {"nodes": 0, "edges": 0, "top_nodes": []}
    if not graph_db_path.exists():
        return empty
    try:
        conn = sqlite3.connect(f"file:{graph_db_path}?mode=ro", uri=True)
        n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        # Compute degree from edges (a and b columns)
        c = Counter()
        for a, b in conn.execute("SELECT a, b FROM edges").fetchall():
            c[a] += 1
            c[b] += 1
        conn.close()
    except Exception:
        return empty
    top = [{"name": name, "degree": deg} for name, deg in c.most_common(10)]
    return {"nodes": n_nodes, "edges": n_edges, "top_nodes": top}


# ─────────────────────────── scan_servers ────────────────────────────

def scan_servers(host: str, ports) -> dict:
    out = {}
    for p in ports:
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect((host, p))
            out[p] = True
        except Exception:
            out[p] = False
        finally:
            s.close()
    return out


# ─────────────────────────── collect_all ─────────────────────────────

def collect_all(
    root,
    *,
    backups_dir: Optional[Path] = None,
    incoming_dir: Optional[Path] = None,
    watermark_db: Optional[Path] = None,
    graph_db_path: Optional[Path] = None,
    host: str = "127.0.0.1",
    ports=None,
) -> dict:
    """Aggregate all scans into one dashboard payload. Defaults derive
    conventional paths from root."""
    root = Path(root)
    if ports is None:
        ports = [9210, 9211, 9212]
    incoming_dir = Path(incoming_dir) if incoming_dir else root / "incoming"
    backups_dir = Path(backups_dir) if backups_dir else root / "backups"
    watermark_db = Path(watermark_db) if watermark_db else root / "synth_wm.db"
    graph_db_path = Path(graph_db_path) if graph_db_path else root / "graph.db"
    return {
        "generated_at": _iso_now(),
        "root": str(root),
        "incoming": scan_incoming(incoming_dir),
        "backups": scan_backups(backups_dir),
        "synth": scan_synth_watermark(watermark_db),
        "graph": scan_graph(graph_db_path),
        "servers": scan_servers(host, ports),
    }
