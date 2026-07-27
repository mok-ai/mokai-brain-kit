"""Tests for LEAF_REGISTRATION.md emission."""
import pytest
from brain_share.leaf_registration import (
    emit_leaf_registration,
    render_leaf_registration,
    PLACEHOLDER_HOST,
)


def test_render_contains_key_and_host_and_version():
    body = render_leaf_registration(read_key="abc123def456",
                                    main_host="main.lan",
                                    version="3.1.1",
                                    today="2026-06-25")
    # Full key appears (it's the copy-paste payload)
    assert "abc123def456" in body
    # Host shows up on both ports
    assert "main.lan:9211" in body
    assert "main.lan:9212" in body
    # Version + date
    assert "Mokai Brain Kit 3.1.1" in body
    assert "2026-06-25" in body
    # All four sections present
    assert "## 1." in body
    assert "## 2." in body
    assert "## 3." in body
    assert "## 4." in body
    # Sub-PC env vars
    assert "BRAIN_INTAKE_URL" in body
    assert "BRAIN_READ_KEY" in body
    assert "AGENT_NAME" in body


def test_emit_writes_file_and_creates_parent_dir(tmp_path):
    target = tmp_path / "new_root"  # does not exist yet
    p = emit_leaf_registration(target, "key1", "host1", "3.1.1",
                               today="2026-06-25")
    assert p.exists()
    assert p.name == "LEAF_REGISTRATION.md"
    assert "key1" in p.read_text(encoding="utf-8")


def test_emit_is_idempotent_preserves_first_key(tmp_path):
    """Second call with different args must NOT overwrite — silently
    rotating the documented read_key would break every registered leaf."""
    p1 = emit_leaf_registration(tmp_path, "first_key", "host1", "3.1.1",
                                today="2026-06-25")
    body1 = p1.read_text(encoding="utf-8")
    p2 = emit_leaf_registration(tmp_path, "second_key", "host2", "9.9.9",
                                today="2099-12-31")
    body2 = p2.read_text(encoding="utf-8")
    assert body1 == body2
    assert "first_key" in body2
    assert "second_key" not in body2
    assert "host1" in body2


def test_emit_uses_placeholder_when_main_host_none(tmp_path):
    p = emit_leaf_registration(tmp_path, "abc", None, "3.1.1",
                               today="2026-06-25")
    body = p.read_text(encoding="utf-8")
    assert PLACEHOLDER_HOST in body
    # Placeholder appears on both port references
    assert f"{PLACEHOLDER_HOST}:9211" in body
    assert f"{PLACEHOLDER_HOST}:9212" in body


def _vbs_run_lines(body: str):
    """Every `WshShell.Run "..."` / `sh.Run "..."` command line in the doc."""
    return [ln.strip() for ln in body.splitlines()
            if ".Run " in ln and ln.strip().startswith(("WshShell.Run",
                                                        "sh.Run"))]


def test_vbs_launcher_wraps_in_cmd_with_logfile():
    """A bare `WshShell.Run "python ...", 0, False` has no stdout handle and
    silently fails to start — no process, no log, and the scheduler still
    records LastResult=0. Every launcher we hand an operator must wrap the
    command in `cmd /c ... > <log> 2>&1` so a failure leaves evidence."""
    body = render_leaf_registration(read_key="k", main_host="main.lan",
                                    version="3.5.0", today="2026-07-27")
    runs = _vbs_run_lines(body)
    assert runs, "template must still ship a VBS launcher"
    for line in runs:
        assert "cmd /c" in line, f"launcher not wrapped in cmd /c: {line}"
        assert "2>&1" in line, f"launcher does not capture stderr: {line}"
        assert ".log" in line, f"launcher writes no logfile: {line}"


def test_vbs_launcher_does_not_use_pythonw():
    """pythonw.exe has no stdout/stderr, so redirecting its output yields an
    empty log — the exact blindness this fix removes. Must be python.exe."""
    body = render_leaf_registration(read_key="k", main_host="main.lan",
                                    version="3.5.0", today="2026-07-27")
    for line in _vbs_run_lines(body):
        assert "pythonw" not in line, f"pythonw defeats logging: {line}"
