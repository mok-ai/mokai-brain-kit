# brain_share_tests/test_dashboard_scanner.py
import json
import sqlite3
from pathlib import Path

import pytest
from brain_share.dashboard_scanner import (
    scan_incoming, scan_backups, scan_synth_watermark,
    scan_graph, scan_servers, collect_all,
)


# ─────────────────────────── scan_incoming ───────────────────────────

def test_scan_incoming_empty_or_missing(tmp_path):
    out = scan_incoming(tmp_path / "nonexistent")
    assert out == {"total_items": 0, "total_size_bytes": 0, "nodes": {}}
    (tmp_path / "empty").mkdir()
    out2 = scan_incoming(tmp_path / "empty")
    assert out2 == {"total_items": 0, "total_size_bytes": 0, "nodes": {}}


def test_scan_incoming_groups_by_node(tmp_path):
    inc = tmp_path / "incoming"
    (inc / "oh").mkdir(parents=True)
    (inc / "oh" / "a.json").write_text('{"content": "hello"}', encoding="utf-8")
    (inc / "oh" / "b.json").write_text('{"content": "world"}', encoding="utf-8")
    (inc / "leaf2").mkdir()
    (inc / "leaf2" / "c.json").write_text('{"content": "x"}', encoding="utf-8")
    out = scan_incoming(inc)
    assert out["total_items"] == 3
    assert set(out["nodes"].keys()) == {"oh", "leaf2"}
    assert out["nodes"]["oh"]["items"] == 2
    assert out["nodes"]["leaf2"]["items"] == 1
    assert out["nodes"]["oh"]["size_bytes"] > 0
    assert out["nodes"]["oh"]["last_ts"] is not None


def test_scan_incoming_ignores_non_json_files(tmp_path):
    inc = tmp_path / "incoming"
    (inc / "oh").mkdir(parents=True)
    (inc / "oh" / "readme.txt").write_text("not counted", encoding="utf-8")
    (inc / "oh" / "a.json").write_text('{"content": "yes"}', encoding="utf-8")
    out = scan_incoming(inc)
    assert out["nodes"]["oh"]["items"] == 1


def test_scan_incoming_survives_stat_race(tmp_path, monkeypatch):
    """A file can be globbed then deleted by a live writer before stat()
    runs (TOCTOU). scan_incoming must skip it, not raise."""
    inc = tmp_path / "incoming"
    (inc / "oh").mkdir(parents=True)
    (inc / "oh" / "a.json").write_text('{"content": "hello"}', encoding="utf-8")
    (inc / "oh" / "b.json").write_text('{"content": "world"}', encoding="utf-8")

    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self.name == "a.json":
            raise FileNotFoundError("vanished before stat")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    out = scan_incoming(inc)
    assert out["nodes"]["oh"]["items"] == 1
    assert out["total_items"] == 1


# ─────────────────────────── scan_backups ────────────────────────────

def test_scan_backups_returns_sorted_newest_first(tmp_path):
    b = tmp_path / "backups"
    for date in ["2026-07-18", "2026-07-19", "2026-07-17"]:
        d = b / date
        d.mkdir(parents=True)
        (d / "chroma_db.zip").write_bytes(b"z" * 100)
        (d / "manifest.json").write_text(json.dumps({
            "date": date, "root": "/x",
            "files": {"chroma_db.zip": {"sha256": "abc12345" + "0"*56, "size": 100}},
        }), encoding="utf-8")
    out = scan_backups(b)
    assert [x["date"] for x in out] == ["2026-07-19", "2026-07-18", "2026-07-17"]
    assert out[0]["sha_prefixes"]["chroma_db.zip"] == "abc12345"
    assert out[0]["size_bytes"] == 100  # sum of files in manifest


def test_scan_backups_missing_dir_returns_empty(tmp_path):
    assert scan_backups(tmp_path / "nonexistent") == []


def test_scan_backups_skips_non_date_named_dirs(tmp_path):
    b = tmp_path / "backups"
    (b / "random_dir").mkdir(parents=True)
    (b / "2026-07-19").mkdir()
    (b / "2026-07-19" / "manifest.json").write_text(
        json.dumps({"date": "2026-07-19", "root": "/x", "files": {}}), encoding="utf-8")
    out = scan_backups(b)
    assert [x["date"] for x in out] == ["2026-07-19"]


def test_scan_backups_skips_malformed_manifest_files_field(tmp_path):
    """A manifest can be valid JSON but the wrong shape: "files" as a list,
    or an entry that's a string instead of a dict. Either must skip that
    backup (no exception) while other valid backups still come back."""
    b = tmp_path / "backups"

    d_list = b / "2026-07-19"
    d_list.mkdir(parents=True)
    (d_list / "manifest.json").write_text(json.dumps({
        "date": "2026-07-19", "root": "/x", "files": ["not", "a", "dict"],
    }), encoding="utf-8")

    d_bad_entry = b / "2026-07-18"
    d_bad_entry.mkdir(parents=True)
    (d_bad_entry / "manifest.json").write_text(json.dumps({
        "date": "2026-07-18", "root": "/x",
        "files": {"chroma_db.zip": "not-a-dict-either"},
    }), encoding="utf-8")

    d_ok = b / "2026-07-17"
    d_ok.mkdir(parents=True)
    (d_ok / "manifest.json").write_text(json.dumps({
        "date": "2026-07-17", "root": "/x",
        "files": {"chroma_db.zip": {"sha256": "abc12345" + "0" * 56, "size": 50}},
    }), encoding="utf-8")

    out = scan_backups(b)
    assert [x["date"] for x in out] == ["2026-07-17"]


# ────────────────────────── scan_synth_watermark ─────────────────────

def test_scan_synth_watermark_missing_returns_empty(tmp_path):
    out = scan_synth_watermark(tmp_path / "ghost.db")
    assert out == {"topics": [], "count": 0}


def test_scan_synth_watermark_reads_topics(tmp_path):
    db = tmp_path / "wm.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE watermark(
        topic TEXT PRIMARY KEY, latest_id TEXT NOT NULL, updated_at REAL)""")
    conn.execute("INSERT INTO watermark VALUES (?,?,?)", ("auth", "abc", 1234.5))
    conn.execute("INSERT INTO watermark VALUES (?,?,?)", ("billing", "def", 5678.9))
    conn.commit()
    conn.close()
    out = scan_synth_watermark(db)
    assert out["count"] == 2
    topics = {t["topic"] for t in out["topics"]}
    assert topics == {"auth", "billing"}


# ─────────────────────────── scan_graph ──────────────────────────────

def test_scan_graph_missing_returns_empty(tmp_path):
    out = scan_graph(tmp_path / "ghost.db")
    assert out == {"nodes": 0, "edges": 0, "top_nodes": []}


def test_scan_graph_counts_and_top_degree(tmp_path):
    db = tmp_path / "graph.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE nodes(name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE edges(a TEXT, b TEXT, weight REAL)")
    for n in ["kim", "epikx", "white", "frog"]:
        conn.execute("INSERT INTO nodes(name) VALUES (?)", (n,))
    # kim connects to 3 others (highest degree)
    for other in ["epikx", "white", "frog"]:
        conn.execute("INSERT INTO edges VALUES (?,?,?)", ("kim", other, 1.0))
    conn.execute("INSERT INTO edges VALUES (?,?,?)", ("epikx", "white", 1.0))
    conn.commit()
    conn.close()
    out = scan_graph(db)
    assert out["nodes"] == 4
    assert out["edges"] == 4
    assert out["top_nodes"][0]["name"] == "kim"
    assert out["top_nodes"][0]["degree"] == 3


# ─────────────────────────── scan_servers ────────────────────────────

def test_scan_servers_all_down_when_ports_unused():
    # Very high ports unlikely to be listened on
    out = scan_servers("127.0.0.1", [59993, 59994, 59995])
    assert out == {59993: False, 59994: False, 59995: False}


def test_scan_servers_detects_live_port(tmp_path):
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        out = scan_servers("127.0.0.1", [port, 59996])
        assert out[port] is True
        assert out[59996] is False
    finally:
        srv.close()


# ─────────────────────────── collect_all ─────────────────────────────

def test_collect_all_returns_all_sections_with_defaults(tmp_path):
    root = tmp_path / "memory"; root.mkdir()
    (root / "incoming").mkdir()
    out = collect_all(root, ports=[59991])
    assert "generated_at" in out
    assert out["root"] == str(root)
    assert "incoming" in out and out["incoming"]["total_items"] == 0
    assert "backups" in out and out["backups"] == []
    assert "synth" in out and out["synth"]["count"] == 0
    assert "graph" in out and out["graph"]["nodes"] == 0
    assert "servers" in out and out["servers"] == {59991: False}


def test_collect_all_never_raises_on_missing_paths(tmp_path):
    """All 4 backing sources absent — collect_all must return empty
    structure per section, no exception."""
    root = tmp_path / "ghost_root"  # doesn't exist
    out = collect_all(root, ports=[])
    assert isinstance(out, dict)
    assert out["incoming"]["total_items"] == 0
    assert out["backups"] == []
    assert out["synth"]["count"] == 0
    assert out["graph"]["nodes"] == 0
