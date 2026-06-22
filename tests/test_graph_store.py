import pytest
from brain_share.graph_store import SqliteGraphStore

@pytest.fixture
def store():
    s = SqliteGraphStore(":memory:")
    yield s
    s.close()

def test_upsert_edge_sorted_and_accumulates(store):
    store.upsert_edge("b", "a", 1.0)
    store.upsert_edge("a", "b", 2.0)            # 같은 무방향 쌍, inc=2.0
    e = store.get_edge("a", "b")
    assert e["a"] == "a" and e["b"] == "b"
    assert e["weight"] == 3.0 and e["count"] == 3.0   # 둘 다 +inc 누적

def test_get_edge_missing_none(store):
    assert store.get_edge("x", "y") is None

def test_decay_all(store):
    store.upsert_edge("a", "b", 10.0)
    store.decay_all(0.5)
    assert store.get_edge("a", "b")["weight"] == 5.0

def test_prune_removes_weak(store):
    store.upsert_edge("a", "b", 1.0)
    store.upsert_edge("a", "c", 0.01)
    removed = store.prune(0.05)
    assert removed == 1
    assert store.get_edge("a", "c") is None
    assert store.get_edge("a", "b") is not None

def test_neighbors_sorted_desc(store):
    store.upsert_edge("a", "b", 1.0)
    store.upsert_edge("a", "c", 5.0)
    store.upsert_edge("a", "d", 3.0)
    ns = store.neighbors("a", top_k=2)
    assert [n["node"] for n in ns] == ["c", "d"]
    assert ns[0]["weight"] == 5.0

def test_node_counts(store):
    store.bump_node("a", 2.0)
    store.bump_node("a", 1.0)
    store.bump_node("b", 4.0)
    assert store.get_node_count("a") == 3.0
    assert store.get_node_count("missing") == 0.0
    assert store.total_node_count() == 7.0

def test_watermark(store):
    assert store.is_processed("u1") is False
    store.mark_processed("u1")
    assert store.is_processed("u1") is True

def test_korean_node_names(store):
    store.upsert_edge("가나", "다라", 1.0)
    assert store.get_edge("다라", "가나")["weight"] == 1.0
    assert store.neighbors("가나")[0]["node"] == "다라"

def test_cross_thread_access(store):
    import threading
    store.upsert_edge("a", "b", 1.0)
    result = {}
    def reader():
        result["w"] = store.get_edge("a", "b")["weight"]
    t = threading.Thread(target=reader); t.start(); t.join()
    assert result["w"] == 1.0
