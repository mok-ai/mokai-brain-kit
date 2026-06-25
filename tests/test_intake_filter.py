import pytest
from brain_share.config import BrainShareConfig
from brain_share.intake_filter import validate_incoming, compute_item_id


def cfg(**kw):
    base = dict(role="HUB", read_key="k", blocked_divisions=["ACCT"],
                allowed_collections=["wiki","knowledge","incoming"],
                blocked_tag_patterns=["고객명단"],
                blocked_keyword_patterns=["api_key"])
    base.update(kw)
    return BrainShareConfig(**base)


def item(**kw):
    base = {"id": "abc123", "content": "hello", "collection": "knowledge",
            "metadata": {"division": "TECH"}}
    base.update(kw)
    return base


def test_compute_item_id_is_deterministic_and_node_scoped():
    a = compute_item_id("node1", "hello")
    b = compute_item_id("node1", "hello")
    c = compute_item_id("node2", "hello")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_accepts_normal_item():
    ok, reason = validate_incoming(item(), cfg(), set())
    assert (ok, reason) == (True, "ok")


def test_rejects_missing_id():
    bad = item(); bad.pop("id")
    ok, reason = validate_incoming(bad, cfg(), set())
    assert (ok, reason) == (False, "missing_id")


def test_rejects_empty_content():
    ok, reason = validate_incoming(item(content=""), cfg(), set())
    assert (ok, reason) == (False, "empty")


def test_rejects_whitespace_content():
    ok, reason = validate_incoming(item(content="   \n\t"), cfg(), set())
    assert (ok, reason) == (False, "empty")


def test_rejects_duplicate_via_seen_ids():
    ok, reason = validate_incoming(item(id="dup1"), cfg(), {"dup1"})
    assert (ok, reason) == (False, "duplicate")


def test_rejects_sensitive_division():
    ok, reason = validate_incoming(item(metadata={"division":"ACCT"}), cfg(), set())
    assert (ok, reason) == (False, "sensitive")


def test_rejects_sensitive_keyword_in_content():
    ok, reason = validate_incoming(item(content="here is api_key=xxx"), cfg(), set())
    assert (ok, reason) == (False, "sensitive")


def test_rejects_sensitive_tag_pattern():
    ok, reason = validate_incoming(
        item(metadata={"division":"TECH","tags":["고객명단"]}), cfg(), set())
    assert (ok, reason) == (False, "sensitive")


def test_rejects_disallowed_collection():
    ok, reason = validate_incoming(item(collection="secrets"), cfg(), set())
    assert (ok, reason) == (False, "sensitive")
