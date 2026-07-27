"""End-to-end tests for brain_watchdog.py (the CLI entry point).

No sockets, no processes: probe and launch are swapped out.
"""
import importlib.util
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]


def load_cli():
    spec = importlib.util.spec_from_file_location(
        "brain_watchdog_under_test", PKG_ROOT / "brain_watchdog.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def write_cfg(root, services, max_failures=3):
    cfg = {"role": "HUB", "read_key": "k",
           "watchdog": {"max_failures": max_failures, "services": services}}
    (root / "brain_share_config.json").write_text(
        json.dumps(cfg), encoding="utf-8")


def test_once_restarts_down_service_and_persists_state(tmp_path):
    cli = load_cli()
    write_cfg(tmp_path, [{"name": "gateway", "port": 9211,
                          "launcher": "wscript g.vbs"}])
    launched = []
    # run_pass is driven directly with an injected probe/launch — main()
    # would open real sockets. Config load and state persistence are still
    # exercised end to end.
    services = cli.services_from_config(
        json.loads((tmp_path / "brain_share_config.json")
                   .read_text(encoding="utf-8")))
    state_path = tmp_path / "watchdog_state.json"
    res = cli.run_pass(services, state_path, 3, log=None,
                       probe=lambda p: False,
                       launch=lambda c: launched.append(c), now=1000.0)
    assert res["restarted"] == ["gateway"]
    assert launched == ["wscript g.vbs"]
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["gateway"]["failures"] == 1


def test_state_survives_between_passes(tmp_path):
    """Second pass inside the grace window must see the first pass's state
    from disk and hold off."""
    cli = load_cli()
    write_cfg(tmp_path, [{"name": "gateway", "port": 9211,
                          "launcher": "wscript g.vbs",
                          "grace_seconds": 300}])
    services = cli.services_from_config(
        json.loads((tmp_path / "brain_share_config.json")
                   .read_text(encoding="utf-8")))
    state_path = tmp_path / "watchdog_state.json"
    calls = []
    cli.run_pass(services, state_path, 3, log=None, probe=lambda p: False,
                 launch=lambda c: calls.append(c), now=1000.0)
    cli.run_pass(services, state_path, 3, log=None, probe=lambda p: False,
                 launch=lambda c: calls.append(c), now=1100.0)
    assert len(calls) == 1, "grace window must survive a process restart"


def test_missing_config_exits_nonzero(tmp_path):
    cli = load_cli()
    assert cli.main(["--root", str(tmp_path), "--once"]) == 2


def test_bad_service_entry_exits_nonzero(tmp_path):
    cli = load_cli()
    write_cfg(tmp_path, [{"name": "gateway"}])  # no port/launcher
    assert cli.main(["--root", str(tmp_path), "--once"]) == 2


def test_no_services_configured_is_success_not_crash(tmp_path):
    cli = load_cli()
    write_cfg(tmp_path, [])
    assert cli.main(["--root", str(tmp_path), "--once"]) == 0
    assert (tmp_path / "watchdog.log").exists()
