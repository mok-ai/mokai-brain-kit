import hashlib
import hmac
import json
import sqlite3

import pytest

from brain_share.config import BrainShareConfig
from brain_share.desk_reporter import (
    DeskSettings,
    build_snapshot,
    desk_settings_from_config,
    main,
    redact_status,
    report_once,
    sign,
    summarize_watchdog,
    verify,
)


def cfg(**kw):
    base = dict(role="HUB", read_key="gateway-key",
                blocked_divisions=["ACCOUNTING", "CUSTOMER"],
                blocked_tag_patterns=["회계"],
                blocked_keyword_patterns=["secret"])
    base.update(kw)
    return BrainShareConfig(**base)


def raw_status():
    return {
        "generated_at": "2026-09-27T10:00:00+09:00",
        "root": "C:/Users/someone/brainkit/memory",
        "incoming": {"total_items": 3, "total_size_bytes": 10,
                     "nodes": {"leaf1": {"items": 3, "size_bytes": 10,
                                         "last_ts": "t"}}},
        "backups": [{"date": "2026-09-27", "size_bytes": 5,
                     "sha_prefixes": {"chroma_db.zip": "abcd1234"}}],
        "synth": {"count": 3, "topics": [
            {"topic": "제품_로드맵", "latest_id": "x", "updated_at": 1},
            {"topic": "회계_결산", "latest_id": "y", "updated_at": 2},
            {"topic": "customer_list", "latest_id": "z", "updated_at": 3},
        ]},
        "graph": {"nodes": 9, "edges": 20, "top_nodes": [
            {"name": "모카이", "degree": 7},
            {"name": "secret_project", "degree": 5},
            {"name": "Accounting", "degree": 4},
        ]},
        "servers": {9210: True, 9211: False},
    }


# ───────────────────────────── redaction ─────────────────────────────

def test_redact_drops_local_root_path():
    out = redact_status(raw_status(), cfg())
    assert "root" not in out
    assert "someone" not in json.dumps(out, ensure_ascii=False)


def test_redact_drops_blocked_graph_nodes_and_topics():
    out = redact_status(raw_status(), cfg())
    names = [n["name"] for n in out["graph"]["top_nodes"]]
    topics = [t["topic"] for t in out["synth"]["topics"]]
    assert names == ["모카이"]
    assert topics == ["제품_로드맵"]
    # Aggregate counts stay: they reveal size, not content.
    assert out["graph"]["nodes"] == 9
    assert out["synth"]["count"] == 3


def test_redact_does_not_mutate_input():
    raw = raw_status()
    before = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    redact_status(raw, cfg())
    assert json.dumps(raw, sort_keys=True, ensure_ascii=False,
                      default=str) == before


def test_redact_tolerates_missing_sections():
    out = redact_status({"generated_at": "t"}, cfg())
    assert out["graph"]["top_nodes"] == []
    assert out["synth"]["topics"] == []


def test_redact_stringifies_server_ports():
    out = redact_status(raw_status(), cfg())
    assert out["servers"] == {"9210": True, "9211": False}


# ───────────────────────────── watchdog ──────────────────────────────

def test_summarize_watchdog_reports_given_up_and_failures():
    state = {"gateway": {"last_restart": 0.0, "failures": 0,
                         "gave_up": False},
             "intake": {"last_restart": 1790000000.0, "failures": 3,
                        "gave_up": True}}
    out = summarize_watchdog(state)
    by = {s["name"]: s for s in out["services"]}
    assert by["intake"]["gave_up"] is True
    assert by["intake"]["failures"] == 3
    assert by["intake"]["last_restart"] is not None
    assert by["gateway"]["last_restart"] is None
    assert out["needs_human"] == ["intake"]


def test_summarize_watchdog_ignores_malformed_entries():
    out = summarize_watchdog({"x": "garbage", "y": {"failures": "bad"}})
    names = [s["name"] for s in out["services"]]
    assert names == ["y"]
    assert out["services"][0]["failures"] == 0


# ───────────────────────────── snapshot ──────────────────────────────

def test_build_snapshot_shape(tmp_path):
    (tmp_path / "watchdog_state.json").write_text(json.dumps(
        {"gateway": {"last_restart": 0, "failures": 1, "gave_up": False}}),
        encoding="utf-8")
    snap = build_snapshot(tmp_path, cfg(), hub_id="main", version="9.9.9",
                          ports=[], now=1790000000.0)
    assert snap["schema"] == "brainkit.desk.v1"
    assert snap["hub_id"] == "main"
    assert snap["version"] == "9.9.9"
    assert snap["sent_at"].startswith("2026-")
    assert "root" not in snap["status"]
    assert snap["watchdog"]["services"][0]["name"] == "gateway"


def test_build_snapshot_redacts_real_graph_db(tmp_path):
    db = sqlite3.connect(tmp_path / "graph.db")
    db.execute("CREATE TABLE nodes (name TEXT)")
    db.execute("CREATE TABLE edges (a TEXT, b TEXT)")
    db.executemany("INSERT INTO edges VALUES (?, ?)",
                   [("모카이", "회계팀"), ("모카이", "제품")])
    db.executemany("INSERT INTO nodes VALUES (?)",
                   [("모카이",), ("회계팀",), ("제품",)])
    db.commit()
    db.close()
    snap = build_snapshot(tmp_path, cfg(), hub_id="main", ports=[])
    names = {n["name"] for n in snap["status"]["graph"]["top_nodes"]}
    assert names == {"모카이", "제품"}


# ───────────────────────────── signing ───────────────────────────────

def test_sign_matches_hmac_over_timestamp_and_body():
    body = b'{"a":1}'
    sig = sign(body, "desk-key", "1790000000")
    expect = hmac.new(b"desk-key", b"1790000000." + body,
                      hashlib.sha256).hexdigest()
    assert sig == expect


def test_verify_accepts_fresh_and_rejects_tampered_or_stale():
    body = b'{"a":1}'
    sig = sign(body, "k", "1000")
    assert verify(body, "k", "1000", sig, now=1100)
    assert not verify(body + b" ", "k", "1000", sig, now=1100)
    assert not verify(body, "other", "1000", sig, now=1100)
    assert not verify(body, "k", "1000", sig, now=1000 + 301)
    assert not verify(body, "k", "not-a-number", sig, now=1100)


# ───────────────────────────── settings ──────────────────────────────

def test_settings_require_url_and_key():
    with pytest.raises(ValueError, match="desk.url"):
        desk_settings_from_config({"desk": {"key": "a"}}, cfg())
    with pytest.raises(ValueError, match="desk.key"):
        desk_settings_from_config(
            {"desk": {"url": "https://x/api"}}, cfg(), env={})


def test_settings_refuse_reusing_gateway_read_key():
    with pytest.raises(ValueError, match="read_key"):
        desk_settings_from_config(
            {"desk": {"url": "https://x/api", "key": "gateway-key"}}, cfg())


def test_settings_refuse_plain_http_except_loopback():
    with pytest.raises(ValueError, match="https"):
        desk_settings_from_config(
            {"desk": {"url": "http://mok.ai.kr/api", "key": "k"}}, cfg())
    s = desk_settings_from_config(
        {"desk": {"url": "http://127.0.0.1:8000/api", "key": "k"}}, cfg())
    assert s.url.startswith("http://127.0.0.1")


def test_settings_key_from_env_and_defaults():
    s = desk_settings_from_config(
        {"desk": {"url": "https://x/api"}}, cfg(),
        env={"BRAIN_DESK_KEY": "from-env"})
    assert s.key == "from-env"
    assert s.hub_id == "main"
    assert s.interval == 300


# ───────────────────────────── report_once ───────────────────────────

def settings():
    return DeskSettings(url="https://desk.example/api/hub-report",
                        key="desk-key", hub_id="main", interval=300)


def test_report_once_posts_signed_body_and_records_success(tmp_path):
    calls = []

    def post(url, body, headers):
        calls.append((url, body, headers))
        return 200, b'{"ok":true}'

    res = report_once(tmp_path, cfg(), settings(), post=post, ports=[],
                      now=1790000000.0)
    assert res["ok"] is True
    url, body, headers = calls[0]
    assert url == "https://desk.example/api/hub-report"
    assert headers["X-Brain-Desk-Hub"] == "main"
    ts = headers["X-Brain-Desk-Timestamp"]
    assert verify(body, "desk-key", ts, headers["X-Brain-Desk-Signature"],
                  now=int(ts))
    # The key itself never travels.
    assert b"desk-key" not in body
    assert "desk-key" not in json.dumps(headers)
    st = json.loads((tmp_path / "desk_reporter_state.json").read_text(
        encoding="utf-8"))
    assert st["last_ok"] is not None
    assert st["consecutive_failures"] == 0


def test_report_once_records_failure_without_raising(tmp_path):
    def post(url, body, headers):
        raise OSError("network down")

    res = report_once(tmp_path, cfg(), settings(), post=post, ports=[])
    assert res["ok"] is False
    assert "network" in res["error"]
    res2 = report_once(tmp_path, cfg(), settings(),
                       post=lambda u, b, h: (500, b"boom"), ports=[])
    assert res2["error"] == "http_500"
    st = json.loads((tmp_path / "desk_reporter_state.json").read_text(
        encoding="utf-8"))
    assert st["consecutive_failures"] == 2
    assert st["last_error"] == "http_500"


# ───────────────────────────── CLI ───────────────────────────────────

def write_cfg(root, desk):
    d = {"role": "HUB", "read_key": "gateway-key",
         "blocked_divisions": ["ACCOUNTING"]}
    if desk is not None:
        d["desk"] = desk
    (root / "brain_share_config.json").write_text(json.dumps(d),
                                                  encoding="utf-8")


def test_cli_once_sends_and_returns_zero(tmp_path):
    write_cfg(tmp_path, {"url": "https://desk.example/api", "key": "dk"})
    sent = []
    rc = main(["--root", str(tmp_path), "--once"],
              post=lambda u, b, h: (sent.append(u), (200, b"{}"))[1])
    assert rc == 0
    assert sent == ["https://desk.example/api"]
    assert (tmp_path / "desk_reporter.log").exists()


def test_cli_once_returns_one_on_send_failure(tmp_path):
    write_cfg(tmp_path, {"url": "https://desk.example/api", "key": "dk"})
    rc = main(["--root", str(tmp_path), "--once"],
              post=lambda u, b, h: (503, b""))
    assert rc == 1


def test_cli_config_error_returns_two(tmp_path):
    write_cfg(tmp_path, None)
    assert main(["--root", str(tmp_path), "--once"],
                post=lambda u, b, h: (200, b"")) == 2


def test_cli_dry_run_prints_without_sending(tmp_path, capsys):
    write_cfg(tmp_path, {"url": "https://desk.example/api", "key": "dk"})

    def post(u, b, h):
        raise AssertionError("dry-run must not send")

    assert main(["--root", str(tmp_path), "--dry-run"], post=post) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "brainkit.desk.v1"
