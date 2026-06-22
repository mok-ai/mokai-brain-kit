import pytest
from brain_share.config import BrainShareConfig
from brain_share.graph_store import SqliteGraphStore
from brain_share.graph_gateway import is_blocked_node, graph_neighbors

def cfg():
    return BrainShareConfig(role="HUB", read_key="k",
                            blocked_tag_patterns=["회계", "손익"],
                            blocked_keyword_patterns=["api_key", "secret"])

@pytest.fixture
def store():
    s = SqliteGraphStore(":memory:")
    s.upsert_edge("acme", "센서", 5.0)
    s.upsert_edge("acme", "회계장부", 4.0)     # 민감(회계)
    s.upsert_edge("acme", "api_key_x", 3.0)    # 시크릿
    s.upsert_edge("acme", "마케팅", 2.0)
    yield s
    s.close()

def test_is_blocked_node():
    c = cfg()
    assert is_blocked_node("회계장부", c) is True
    assert is_blocked_node("API_KEY_x", c) is True
    assert is_blocked_node("센서", c) is False

def test_graph_neighbors_filters_sensitive(store):
    out = graph_neighbors("acme", top_k=10, store=store, config=cfg())
    names = [n["node"] for n in out]
    assert "센서" in names and "마케팅" in names
    assert "회계장부" not in names and "api_key_x" not in names

def test_graph_neighbors_topk(store):
    out = graph_neighbors("acme", top_k=1, store=store, config=cfg())
    assert len(out) == 1 and out[0]["node"] == "센서"   # weight 최고

def test_graph_neighbors_blocked_query_empty(store):
    out = graph_neighbors("api_key", top_k=5, store=store, config=cfg())
    assert out == []

def test_is_blocked_node_empty_patterns_no_false_positive():
    from brain_share.config import BrainShareConfig
    c = BrainShareConfig(role="HUB", read_key="k",
                         blocked_tag_patterns=["", "회계"],
                         blocked_keyword_patterns=[""])
    assert is_blocked_node("센서", c) is False
    assert is_blocked_node("회계장부", c) is True

def test_graph_neighbors_skips_rows_missing_node_key(store):
    class BadStore:
        def neighbors(self, node, top_k):
            return [{"weight": 9.0, "count": 1.0}, {"node": "센서", "weight": 5.0, "count": 1.0}]
    out = graph_neighbors("acme", top_k=5, store=BadStore(), config=cfg())
    assert [n["node"] for n in out] == ["센서"]

def test_is_blocked_node_tag_case_insensitive():
    from brain_share.config import BrainShareConfig
    c = BrainShareConfig(role="HUB", read_key="k", blocked_tag_patterns=["Secret"])
    assert is_blocked_node("my_secret_doc", c) is True
