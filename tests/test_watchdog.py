"""Tests for the self-healing watchdog.

Everything here is deterministic: the port probe, the launcher and the clock
are all injected, so no sockets are opened and no processes are spawned.
"""
import json

import pytest

from brain_share.watchdog import (
    ServiceSpec,
    check_once,
    load_state,
    save_state,
)


def svc(name="gateway", port=9211, grace=300):
    return ServiceSpec(name=name, port=port,
                       launcher=f"wscript start_{name}.vbs",
                       grace_seconds=grace)


class Launcher:
    """Records what it was asked to start."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, cmd):
        self.calls.append(cmd)
        if self.fail:
            raise OSError("launch blew up")


def probe_all(up):
    return lambda port: up


# ───────────────────────────── happy paths ────────────────────────────

def test_all_up_restarts_nothing():
    lau = Launcher()
    res = check_once([svc()], probe=probe_all(True), launch=lau,
                     state={}, now=1000.0)
    assert lau.calls == []
    assert res["restarted"] == []
    assert res["up"] == ["gateway"]


def test_down_service_is_restarted():
    lau = Launcher()
    state = {}
    res = check_once([svc()], probe=probe_all(False), launch=lau,
                     state=state, now=1000.0)
    assert lau.calls == ["wscript start_gateway.vbs"]
    assert res["restarted"] == ["gateway"]
    assert state["gateway"]["failures"] == 1
    assert state["gateway"]["last_restart"] == 1000.0


def test_recovered_service_resets_failure_count():
    state = {"gateway": {"last_restart": 500.0, "failures": 2,
                         "gave_up": False}}
    lau = Launcher()
    check_once([svc()], probe=probe_all(True), launch=lau, state=state,
               now=2000.0)
    assert state["gateway"]["failures"] == 0
    assert state["gateway"]["gave_up"] is False
    assert lau.calls == []


# ─────────────────────── restart storm protection ─────────────────────

def test_grace_window_suppresses_immediate_recheck():
    """A service that takes 90s to load its model is still DOWN one minute
    after we started it. Restarting again would stack processes forever."""
    state = {"gateway": {"last_restart": 1000.0, "failures": 1,
                         "gave_up": False}}
    lau = Launcher()
    res = check_once([svc(grace=300)], probe=probe_all(False), launch=lau,
                     state=state, now=1100.0)  # 100s < 300s grace
    assert lau.calls == []
    assert res["restarted"] == []
    assert "gateway" in res["grace"]
    assert state["gateway"]["failures"] == 1  # not incremented


def test_holding_off_is_logged_not_silent():
    """'Held off on purpose' and 'the watchdog never ran' look identical in
    an empty log. That ambiguity cost real debugging time on 2026-07-27."""
    lines = []
    state = {"gateway": {"last_restart": 1000.0, "failures": 1,
                         "gave_up": False}}
    check_once([svc(grace=300)], probe=probe_all(False), launch=Launcher(),
               state=state, now=1100.0, log=lines.append)
    assert lines, "grace must leave a trace"
    assert "grace" in lines[0] and "100s" in lines[0]


def test_given_up_service_keeps_reporting_itself():
    """Silence after giving up would read as 'all healthy'."""
    lines = []
    state = {"gateway": {"last_restart": 1.0, "failures": 3,
                         "gave_up": True}}
    check_once([svc()], probe=probe_all(False), launch=Launcher(),
               state=state, now=9000.0, log=lines.append)
    assert lines and "given up" in lines[0]


def test_restart_again_once_grace_expired():
    state = {"gateway": {"last_restart": 1000.0, "failures": 1,
                         "gave_up": False}}
    lau = Launcher()
    check_once([svc(grace=300)], probe=probe_all(False), launch=lau,
               state=state, now=1400.0)  # 400s > 300s
    assert lau.calls == ["wscript start_gateway.vbs"]
    assert state["gateway"]["failures"] == 2


def test_gives_up_after_max_failures_and_stops_trying():
    """Something is structurally broken (bad path, missing python). Retrying
    every 5 minutes forever just fills the disk with logs."""
    lau = Launcher()
    state = {}
    now = 1000.0
    for _ in range(3):
        check_once([svc(grace=0)], probe=probe_all(False), launch=lau,
                   state=state, now=now)
        now += 1.0
    assert len(lau.calls) == 3
    assert state["gateway"]["gave_up"] is True

    res = check_once([svc(grace=0)], probe=probe_all(False), launch=lau,
                     state=state, now=now)
    assert len(lau.calls) == 3, "must not retry after giving up"
    assert res["gave_up"] == ["gateway"]


def test_gave_up_service_recovers_when_it_comes_back():
    """Operator fixes the launcher by hand — the watchdog must forgive and
    resume guarding it, without needing its state file deleted."""
    state = {"gateway": {"last_restart": 1.0, "failures": 3,
                         "gave_up": True}}
    lau = Launcher()
    check_once([svc()], probe=probe_all(True), launch=lau, state=state,
               now=9000.0)
    assert state["gateway"]["gave_up"] is False
    assert state["gateway"]["failures"] == 0


# ───────────────────────────── robustness ─────────────────────────────

def test_launcher_exception_does_not_kill_the_pass():
    """One broken launcher must not stop the other services being checked."""
    lau = Launcher(fail=True)
    state = {}
    res = check_once([svc("gateway", 9211), svc("intake", 9212)],
                     probe=probe_all(False), launch=lau, state=state,
                     now=1000.0)
    assert len(lau.calls) == 2, "second service still attempted"
    assert res["errors"] and "gateway" in res["errors"][0]
    assert res["restarted"] == []


def test_probe_exception_treated_as_down():
    def boom(port):
        raise OSError("socket layer angry")

    lau = Launcher()
    res = check_once([svc()], probe=boom, launch=lau, state={}, now=1000.0)
    assert lau.calls == ["wscript start_gateway.vbs"]
    assert res["restarted"] == ["gateway"]


# ──────────────────────────── state file ──────────────────────────────

def test_state_roundtrip(tmp_path):
    p = tmp_path / "watchdog_state.json"
    state = {"gateway": {"last_restart": 12.5, "failures": 1,
                         "gave_up": False}}
    save_state(p, state)
    assert load_state(p) == state


def test_load_state_missing_file_returns_empty(tmp_path):
    assert load_state(tmp_path / "nope.json") == {}


def test_load_state_corrupt_file_returns_empty(tmp_path):
    """A half-written state file must not stop the watchdog from running —
    losing the counters is survivable, refusing to guard anything is not."""
    p = tmp_path / "watchdog_state.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_state(p) == {}


def test_save_state_is_atomic_enough_to_reread(tmp_path):
    p = tmp_path / "s.json"
    save_state(p, {"a": {"failures": 1}})
    save_state(p, {"a": {"failures": 2}})
    assert json.loads(p.read_text(encoding="utf-8"))["a"]["failures"] == 2


# ──────────────────────────── spec parsing ────────────────────────────

def test_services_from_config_dict():
    from brain_share.watchdog import services_from_config
    cfg = {"watchdog": {"services": [
        {"name": "gateway", "port": 9211, "launcher": "wscript g.vbs"},
        {"name": "intake", "port": 9212, "launcher": "wscript i.vbs",
         "grace_seconds": 60},
    ]}}
    specs = services_from_config(cfg)
    assert [s.name for s in specs] == ["gateway", "intake"]
    assert specs[0].grace_seconds == 300  # default
    assert specs[1].grace_seconds == 60


def test_services_from_config_missing_section_is_empty():
    from brain_share.watchdog import services_from_config
    assert services_from_config({}) == []


def test_services_from_config_rejects_incomplete_entry():
    from brain_share.watchdog import services_from_config
    with pytest.raises(ValueError):
        services_from_config({"watchdog": {"services": [{"name": "x"}]}})


# ───────────────── launcher -> argv (no shell, ever) ──────────────────

def test_argv_for_keeps_windows_backslashes():
    from brain_share.watchdog import argv_for
    assert argv_for(r"wscript C:\main_ai\start_gateway.vbs") == [
        "wscript", r"C:\main_ai\start_gateway.vbs"]


def test_argv_for_strips_quotes_around_spaced_path():
    from brain_share.watchdog import argv_for
    assert argv_for('wscript "C:/Program Files/x.vbs"') == [
        "wscript", "C:/Program Files/x.vbs"]


def test_argv_for_passes_list_through():
    from brain_share.watchdog import argv_for
    assert argv_for(["wscript", "C:/a b/x.vbs"]) == ["wscript", "C:/a b/x.vbs"]


def test_argv_for_rejects_empty():
    from brain_share.watchdog import argv_for
    with pytest.raises(ValueError):
        argv_for("   ")


def test_launcher_is_never_run_through_a_shell():
    """Shell metacharacters must survive as literal argv text, not be
    interpreted. If this ever regresses, a config string becomes code."""
    from brain_share.watchdog import argv_for
    argv = argv_for('wscript x.vbs && calc.exe')
    assert "&&" in argv, "tokens preserved verbatim"
    assert argv[0] == "wscript"
    # the point: Popen(argv) hands these to wscript as arguments; there is no
    # shell to act on '&&'.
