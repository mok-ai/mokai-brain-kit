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
