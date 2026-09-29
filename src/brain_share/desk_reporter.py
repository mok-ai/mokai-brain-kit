"""Hub -> desk status reporter (outbound push, stdlib only).

The remote desk (e.g. an admin web dashboard) must never reach into the hub:
the hub sits on 127.0.0.1 and its dashboard has no auth. Instead the hub
*pushes* a redacted summary out, the same direction leaf -> main uploads
already travel. No inbound port is opened.

What leaves the machine
-----------------------
* dashboard_scanner.collect_all() minus the local `root` path, with graph
  top-nodes and synth topic names dropped when they match blocked_divisions,
  blocked_tag_patterns or blocked_keyword_patterns. Aggregate counts stay —
  they reveal size, not content.
* A watchdog summary (per-service failures / given-up) from
  watchdog_state.json, so the desk can flag "needs a human".
* Task board counts (per status, awaiting approval, blocked, overdue) from
  task_board.db — numbers only, never titles or text. `null` if no board.

Auth
----
The body is signed with HMAC-SHA256 over "<unix ts>.<body>" using a desk-only
key. The key itself never travels. The gateway read_key is refused as a desk
key: one leaked secret must not open both doors. Receivers should call
verify() (or port it) and reject stale timestamps to stop replays.

Run it like the watchdog — from Task Scheduler with --once every 5 minutes —
so there is no resident process to die. The desk treats a missing report as
"hub unreachable", which also covers the hub machine being off.

    python -m brain_share.desk_reporter --root C:/brainkit/memory --once
    python -m brain_share.desk_reporter --root C:/brainkit/memory --dry-run

Configure in brain_share_config.json (key may come from $BRAIN_DESK_KEY):

    "desk": {"url": "https://mok.ai.kr/api/hub-report",
             "key": "<desk-only secret>", "hub_id": "main", "interval": 300}
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from brain_share.config import BrainShareConfig, load_config
from brain_share.dashboard_scanner import collect_all
from brain_share.graph_gateway import is_blocked_node
from brain_share.task_board import read_summary
from brain_share.watchdog import load_state, save_state

SCHEMA = "brainkit.desk.v1"
DEFAULT_INTERVAL = 300
DEFAULT_MAX_SKEW = 300
STATE_FILE = "desk_reporter_state.json"
LOG_FILE = "desk_reporter.log"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


# ───────────────────────────── redaction ─────────────────────────────

def _is_blocked_name(name, config: BrainShareConfig) -> bool:
    if is_blocked_node(name, config):
        return True
    low = str(name).lower()
    return any(d and d.lower() in low for d in config.blocked_divisions)


def redact_status(status: dict, config: BrainShareConfig) -> dict:
    """Copy of a collect_all() payload that is safe to send off-machine."""
    out = copy.deepcopy(status or {})
    out.pop("root", None)  # local filesystem path — may carry an account name

    graph = out.get("graph") or {}
    graph["top_nodes"] = [
        n for n in (graph.get("top_nodes") or [])
        if isinstance(n, dict) and not _is_blocked_name(n.get("name", ""), config)
    ]
    out["graph"] = graph

    synth = out.get("synth") or {}
    synth["topics"] = [
        t for t in (synth.get("topics") or [])
        if isinstance(t, dict) and not _is_blocked_name(t.get("topic", ""), config)
    ]
    out["synth"] = synth

    # JSON object keys are strings anyway; make it explicit so the signed
    # bytes don't depend on how a serializer treats int keys.
    out["servers"] = {str(k): bool(v) for k, v in (out.get("servers") or {}).items()}
    return out


# ───────────────────────────── watchdog ──────────────────────────────

def summarize_watchdog(state: dict) -> dict:
    services = []
    for name, st in sorted((state or {}).items()):
        if not isinstance(st, dict):
            continue
        try:
            failures = int(st.get("failures", 0) or 0)
        except (TypeError, ValueError):
            failures = 0
        try:
            last = float(st.get("last_restart", 0) or 0)
        except (TypeError, ValueError):
            last = 0.0
        services.append({
            "name": str(name),
            "failures": failures,
            "gave_up": bool(st.get("gave_up", False)),
            "last_restart": _iso(last) if last > 0 else None,
        })
    return {"services": services,
            "needs_human": [s["name"] for s in services if s["gave_up"]]}


# ───────────────────────────── snapshot ──────────────────────────────

def _package_version() -> str:
    for base in (Path(__file__).resolve().parents[1],
                 Path(__file__).resolve().parents[2]):
        try:
            return (base / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return "unknown"


def build_snapshot(root, config: BrainShareConfig, *, hub_id: str = "main",
                   version: str = None, ports=None, now: float = None) -> dict:
    root = Path(root)
    now = time.time() if now is None else now
    return {
        "schema": SCHEMA,
        "hub_id": hub_id,
        "version": version or _package_version(),
        "sent_at": _iso(now),
        "status": redact_status(collect_all(root, ports=ports), config),
        "watchdog": summarize_watchdog(load_state(root / "watchdog_state.json")),
        "board": read_summary(root / "task_board.db"),
    }


# ───────────────────────────── signing ───────────────────────────────

def sign(body: bytes, key: str, timestamp: str) -> str:
    msg = str(timestamp).encode("ascii") + b"." + body
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify(body: bytes, key: str, timestamp: str, signature: str, *,
           now: float = None, max_skew: int = DEFAULT_MAX_SKEW) -> bool:
    """Receiver-side check. Reference implementation for the desk."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    now = time.time() if now is None else now
    if abs(now - ts) > max_skew:
        return False
    return hmac.compare_digest(sign(body, key, str(ts)), str(signature))


# ───────────────────────────── settings ──────────────────────────────

@dataclass
class DeskSettings:
    url: str
    key: str
    hub_id: str = "main"
    interval: int = DEFAULT_INTERVAL


def desk_settings_from_config(raw: dict, config: BrainShareConfig,
                              env=None) -> DeskSettings:
    env = os.environ if env is None else env
    d = (raw or {}).get("desk") or {}
    url = str(d.get("url") or "").strip()
    if not url:
        raise ValueError("desk.url is not set")
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in _LOOPBACK):
        raise ValueError("desk.url must be https (plain http only to loopback)")
    key = str(d.get("key") or env.get("BRAIN_DESK_KEY") or "")
    if not key:
        raise ValueError("desk.key is not set (or $BRAIN_DESK_KEY)")
    if config.read_key and key == config.read_key:
        raise ValueError("desk.key must differ from the gateway read_key")
    return DeskSettings(url=url, key=key,
                        hub_id=str(d.get("hub_id") or "main"),
                        interval=int(d.get("interval") or DEFAULT_INTERVAL))


# ───────────────────────────── sending ───────────────────────────────

def _default_post(url: str, body: bytes, headers: dict):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def report_once(root, config: BrainShareConfig, settings: DeskSettings, *,
                post=None, ports=None, now: float = None) -> dict:
    """Build, sign and send one snapshot. Never raises on network trouble;
    the outcome is persisted to desk_reporter_state.json either way."""
    root = Path(root)
    post = post or _default_post
    now = time.time() if now is None else now
    snap = build_snapshot(root, config, hub_id=settings.hub_id, ports=ports,
                          now=now)
    body = json.dumps(snap, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ts = str(int(now))
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Brain-Desk-Hub": settings.hub_id,
        "X-Brain-Desk-Timestamp": ts,
        "X-Brain-Desk-Signature": sign(body, settings.key, ts),
    }
    try:
        status, _ = post(settings.url, body, headers)
        error = None if status == 200 else f"http_{status}"
    except Exception as e:  # network, DNS, TLS — reported, not raised
        error = f"network: {e}"

    state_path = root / STATE_FILE
    state = load_state(state_path)
    if error is None:
        state.update(last_ok=_iso(now), consecutive_failures=0)
    else:
        state.setdefault("last_ok", None)
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        state["last_error"] = error
        state["last_error_at"] = _iso(now)
    save_state(state_path, state)
    return {"ok": error is None, "error": error, "bytes": len(body)}


# ───────────────────────────── CLI ───────────────────────────────────

def _logger(path: Path):
    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, file=sys.stderr)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    return log


def main(argv=None, post=None) -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            if _s is not None and hasattr(_s, "reconfigure"):
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="brain_share.desk_reporter",
        description="Push a redacted hub status snapshot to the desk")
    ap.add_argument("--root", required=True,
                    help="memory root (holds brain_share_config.json)")
    ap.add_argument("--config", default=None,
                    help="config path (default <root>/brain_share_config.json)")
    ap.add_argument("--once", action="store_true",
                    help="single report then exit (use with Task Scheduler)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the redacted snapshot, send nothing")
    args = ap.parse_args(argv)

    root = Path(args.root)
    cfg_path = Path(args.config) if args.config \
        else root / "brain_share_config.json"
    try:
        config = load_config(str(cfg_path))
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"config unreadable: {cfg_path}: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        hub_id = str(((raw.get("desk") or {}).get("hub_id")) or "main")
        print(json.dumps(build_snapshot(root, config, hub_id=hub_id),
                         ensure_ascii=False, indent=1, sort_keys=True))
        return 0

    try:
        settings = desk_settings_from_config(raw, config)
    except ValueError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    log = _logger(root / LOG_FILE)

    def one() -> bool:
        res = report_once(root, config, settings, post=post)
        if res["ok"]:
            log(f"report ok ({res['bytes']} bytes) -> {settings.url}")
        else:
            log(f"report FAILED: {res['error']}")
        return res["ok"]

    if args.once:
        return 0 if one() else 1

    log(f"desk reporter resident, interval={settings.interval}s")
    while True:
        one()
        time.sleep(settings.interval)


if __name__ == "__main__":
    raise SystemExit(main())
