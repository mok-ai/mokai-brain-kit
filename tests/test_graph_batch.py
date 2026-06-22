import pytest
from brain_share.graph_store import SqliteGraphStore
from brain_share.graph_batch import update_graph


@pytest.fixture
def store():
    s = SqliteGraphStore(":memory:")
    yield s
    s.close()


def test_cooccurrence_builds_edges(store):
    units = [("u1", ["a", "b", "c"])]
    rep = update_graph(units, store, decay=1.0, prune_min=0.0)
    assert rep["processed"] == 1
    assert store.get_edge("a", "b")["weight"] == 1.0
    assert store.get_edge("b", "c")["weight"] == 1.0
    assert store.get_edge("a", "c")["weight"] == 1.0


def test_idempotent_same_unit(store):
    units = [("u1", ["a", "b"])]
    update_graph(units, store, decay=1.0, prune_min=0.0)
    rep2 = update_graph(units, store, decay=1.0, prune_min=0.0)   # 재투입
    assert rep2["processed"] == 0 and rep2["skipped"] == 1
    assert store.get_edge("a", "b")["weight"] == 1.0             # 중복 집계 없음


def test_decay_applied_once_per_call(store):
    update_graph([("u1", ["a", "b"])], store, decay=1.0, prune_min=0.0)  # weight 1.0
    update_graph([("u2", ["a", "b"])], store, decay=0.5, prune_min=0.0)  # decay→0.5, +1 →1.5
    assert store.get_edge("a", "b")["weight"] == 1.5


def test_canonicalize_merges_nodes(store):
    amap = {"ACME": "joydu", "ACMEE": "joydu"}
    units = [("u1", ["ACME", "x"]), ("u2", ["ACMEE", "x"])]
    update_graph(units, store, canonicalize=lambda n: amap.get(n, n), decay=1.0, prune_min=0.0)
    # 두 변형이 한 노드(joydu)로 → joydu-x 엣지에 누적
    assert store.get_edge("joydu", "x")["weight"] == 2.0


def test_prune_after_update(store):
    update_graph([("u1", ["a", "b"])], store, decay=1.0, prune_min=0.0)   # edge weight 1.0
    update_graph([("u2", ["x", "y"])], store, decay=0.01, prune_min=0.5)  # a-b decays to 0.01 → pruned
    assert store.get_edge("a", "b") is None
    assert store.get_edge("x", "y") is not None


def test_decay_fires_on_empty_input(store):
    update_graph([("u1", ["a", "b"])], store, decay=1.0, prune_min=0.0)   # weight 1.0
    rep = update_graph([], store, decay=0.5, prune_min=0.0)               # no new units, still decays
    assert rep["processed"] == 0
    assert store.get_edge("a", "b")["weight"] == 0.5
