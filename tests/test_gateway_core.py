from brain_share.config import BrainShareConfig
from brain_share.gateway_core import check_key, resolve_query, resolve_related

def cfg():
    return BrainShareConfig(role="HUB", read_key="secret-key",
                            allowed_collections=["wiki", "knowledge"],
                            blocked_divisions=["ACCT"])

def W(id, content="wiki 정본", division="TECH"):
    return {"id": id, "content": content, "score": 0.95, "collection": "wiki",
            "metadata": {"division": division}}

def K(id, content="rag 조각", division="TECH"):
    return {"id": id, "content": content, "score": 0.8, "collection": "knowledge",
            "metadata": {"division": division}}

def test_check_key():
    assert check_key("secret-key", cfg()) is True
    assert check_key("wrong", cfg()) is False
    assert check_key("", cfg()) is False

def test_wiki_first_then_fallback():
    wiki = lambda q, k: [W("w1")]
    rag = lambda q, k: [K("r1"), K("r2")]
    out = resolve_query("q", 3, wiki, rag, cfg())
    ids = [r["id"] for r in out]
    assert ids[0] == "w1" and "r1" in ids and len(out) == 3

def test_filter_applied_to_both():
    wiki = lambda q, k: [W("w1", division="ACCT")]      # blocked
    rag = lambda q, k: [K("r1", division="ACCT"), K("r2")]  # r1 blocked
    out = resolve_query("q", 5, wiki, rag, cfg())
    assert [r["id"] for r in out] == ["r2"]

def test_no_duplicate_ids():
    wiki = lambda q, k: [W("dup")]
    rag = lambda q, k: [K("dup"), K("r2")]
    out = resolve_query("q", 5, wiki, rag, cfg())
    assert [r["id"] for r in out].count("dup") == 1

def test_wiki_enough_skips_fallback_excess():
    wiki = lambda q, k: [W("w1"), W("w2")]
    rag = lambda q, k: [K("r1")]
    out = resolve_query("q", 2, wiki, rag, cfg())
    assert [r["id"] for r in out] == ["w1", "w2"]

def test_resolve_related_filters_blocked():
    related = lambda e, k: [K("r1", division="ACCT"), K("r2"), W("w3")]
    out = resolve_related("ent", 10, related, cfg())
    assert [r["id"] for r in out] == ["r2", "w3"]  # ACCT dropped

def test_resolve_related_empty():
    assert resolve_related("ent", 5, lambda e, k: [], cfg()) == []
