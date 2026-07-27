"""Self-healing watchdog for the hub daemons.

Registering a launcher is not the same as it running: on 2026-07-27 all four
autostart entries were present, enabled and backed by a real interactive
logon, and not one daemon came up after a reboot — with no log to say so.
Something has to notice.

Design notes
------------
* The probe, the launcher and the clock are injected, so the decision logic
  is pure and testable without sockets or processes.
* A *grace window* after each restart stops us stacking processes on top of a
  service that is simply slow to boot (the gateway loads an embedding model).
* After `max_failures` consecutive restarts that don't take, the service is
  *given up on* — a structurally broken launcher should be reported once, not
  retried every five minutes forever. Seeing the service healthy again clears
  the flag, so a hand-fix needs no state surgery.
* Nothing here restarts the watchdog itself. That is deliberate: run this
  from Task Scheduler with `--once` every few minutes and there is no
  resident process to die — which is the observer problem the dashboard has.
"""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GRACE_SECONDS = 300
DEFAULT_MAX_FAILURES = 3


@dataclass
class ServiceSpec:
    name: str
    port: int
    # str (parsed into argv) or an explicit argument list. Never run through
    # a shell — see argv_for().
    launcher: object
    grace_seconds: int = DEFAULT_GRACE_SECONDS


def argv_for(launcher) -> list[str]:
    """Turn a configured launcher into an argument list for Popen.

    A list is taken as-is (the unambiguous form, and the one to prefer when a
    path contains spaces). A string is split with POSIX rules off so Windows
    backslashes survive, then surrounding quotes are stripped from each token.
    Callers must never hand the raw string to a shell: the config is a local
    trusted file, but a launcher is no place to accept shell syntax.
    """
    if isinstance(launcher, (list, tuple)):
        argv = [str(a) for a in launcher]
    else:
        argv = shlex.split(str(launcher), posix=False)
        argv = [a[1:-1] if len(a) > 1 and a[0] == a[-1] == '"' else a
                for a in argv]
    if not argv:
        raise ValueError("empty launcher")
    return argv


def services_from_config(cfg: dict) -> list[ServiceSpec]:
    """Read the optional `watchdog.services` section of brain_share_config.

    Absent section means "guard nothing" (valid — a leaf has no daemons).
    A malformed entry is an error: silently skipping it would leave an
    operator believing a service is guarded when it isn't.
    """
    section = (cfg or {}).get("watchdog") or {}
    out = []
    for i, entry in enumerate(section.get("services", []) or []):
        missing = [k for k in ("name", "port", "launcher") if not entry.get(k)]
        if missing:
            raise ValueError(
                f"watchdog.services[{i}] missing required key(s): "
                f"{', '.join(missing)}")
        out.append(ServiceSpec(
            name=str(entry["name"]),
            port=int(entry["port"]),
            launcher=entry["launcher"],
            grace_seconds=int(entry.get("grace_seconds",
                                        DEFAULT_GRACE_SECONDS)),
        ))
    return out


def _entry(state: dict, name: str) -> dict:
    return state.setdefault(
        name, {"last_restart": 0.0, "failures": 0, "gave_up": False})


def check_once(services, *, probe, launch, state, now,
               max_failures: int = DEFAULT_MAX_FAILURES,
               log=None) -> dict:
    """Probe every service once and restart what is down.

    `state` is mutated in place (and is what you persist between runs).
    Returns a summary dict — the caller logs/prints it.
    """
    result = {"up": [], "restarted": [], "grace": [], "gave_up": [],
              "errors": []}

    def say(msg):
        if log:
            log(msg)

    for s in services:
        try:
            alive = bool(probe(s.port))
        except Exception:
            alive = False  # an unusable probe means we can't call it healthy

        st = _entry(state, s.name)

        if alive:
            if st["failures"] or st["gave_up"]:
                say(f"{s.name}: recovered, clearing {st['failures']} failure(s)")
            st["failures"] = 0
            st["gave_up"] = False
            result["up"].append(s.name)
            continue

        if st["gave_up"]:
            result["gave_up"].append(s.name)
            continue

        if now - st["last_restart"] < s.grace_seconds:
            result["grace"].append(s.name)
            continue

        try:
            launch(s.launcher)
        except Exception as exc:
            msg = f"{s.name}: launcher failed: {exc}"
            result["errors"].append(msg)
            say(msg)
            continue
        finally:
            # A launcher that raised still counts as an attempt — otherwise a
            # permanently broken command retries every pass forever.
            st["last_restart"] = now
            st["failures"] += 1
            if st["failures"] >= max_failures:
                st["gave_up"] = True
                say(f"{s.name}: giving up after {st['failures']} attempts")

        result["restarted"].append(s.name)
        say(f"{s.name}: DOWN on :{s.port} -> restarted "
            f"(attempt {st['failures']}/{max_failures})")

    return result


# ──────────────────────────── state file ──────────────────────────────

def load_state(path) -> dict:
    """Never raises. A missing or corrupt state file costs us the failure
    counters, which is survivable; refusing to run is not."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    tmp.replace(path)
