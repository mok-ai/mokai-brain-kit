"""Mokai Brain Kit — daemon watchdog (self-healing autostart).

Probes each configured service's port and restarts whatever is down, with a
grace window and a give-up threshold so a slow boot or a broken launcher
can't turn into a restart storm.

Recommended: run with --once from Task Scheduler every 5 minutes. Then the
watchdog has no resident process of its own to die — unlike the dashboard,
which cannot report that it is itself down.

    python brain_watchdog.py --root C:/main_ai/memory --once
    python brain_watchdog.py --root C:/main_ai/memory --interval 300

Configure in brain_share_config.json:

    "watchdog": {
      "max_failures": 3,
      "services": [
        {"name": "gateway",   "port": 9211,
         "launcher": "wscript C:/main_ai/start_gateway.vbs"},
        {"name": "intake",    "port": 9212,
         "launcher": "wscript C:/main_ai/start_intake.vbs"},
        {"name": "dashboard", "port": 9213,
         "launcher": "wscript C:/main_ai/start_dashboard.vbs",
         "grace_seconds": 60}
      ]
    }

Only port-backed services are guarded. A daemon with no listening socket
(synth_daemon) cannot be probed this way and is out of scope for now.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain_share.watchdog import (  # noqa: E402
    DEFAULT_MAX_FAILURES,
    argv_for,
    check_once,
    load_state,
    save_state,
    services_from_config,
)

PROBE_TIMEOUT = 0.5


def probe_port(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket()
    s.settimeout(PROBE_TIMEOUT)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def spawn(cmd) -> None:
    """Start a launcher fully detached, so it outlives this process.

    Runs without a shell: the launcher is turned into an argument list, so
    nothing in the config string can be read as a shell metacharacter.
    """
    argv = argv_for(cmd)
    kwargs = {}
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **kwargs)


def make_logger(log_path: Path):
    def log(msg: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{stamp} {msg}"
        print(line)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass  # logging must never take the watchdog down
    return log


def run_pass(services, state_path, max_failures, log, *,
             probe=probe_port, launch=spawn, now=None) -> dict:
    state = load_state(state_path)
    res = check_once(services, probe=probe, launch=launch, state=state,
                     now=time.time() if now is None else now,
                     max_failures=max_failures, log=log)
    save_state(state_path, state)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Brain Kit daemon watchdog")
    ap.add_argument("--root", required=True,
                    help="memory root (holds brain_share_config.json)")
    ap.add_argument("--config", default=None,
                    help="config path (default <root>/brain_share_config.json)")
    ap.add_argument("--once", action="store_true",
                    help="single pass then exit (use with Task Scheduler)")
    ap.add_argument("--interval", type=int, default=300,
                    help="seconds between passes when resident")
    args = ap.parse_args(argv)

    root = Path(args.root)
    cfg_path = Path(args.config) if args.config \
        else root / "brain_share_config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"config unreadable: {cfg_path}: {exc}", file=sys.stderr)
        return 2

    try:
        services = services_from_config(cfg)
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    log = make_logger(root / "watchdog.log")
    if not services:
        log("no watchdog.services configured — nothing to guard")
        return 0

    max_failures = int((cfg.get("watchdog") or {}).get(
        "max_failures", DEFAULT_MAX_FAILURES))
    state_path = root / "watchdog_state.json"

    def one():
        res = run_pass(services, state_path, max_failures, log)
        if res["restarted"] or res["errors"] or res["gave_up"]:
            log(f"pass: {res}")
        return res

    if args.once:
        one()
        return 0

    log(f"watchdog resident, interval={args.interval}s, "
        f"guarding {[s.name for s in services]}")
    while True:
        one()
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
