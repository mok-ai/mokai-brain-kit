"""Tests for selfsynth_batch — pure logic only, no chroma/sklearn/claude."""
import numpy as np
import pytest

from brain_share.selfsynth_batch import (
    cluster_topics,
    pick_representatives,
    run_selfsynth,
)


# ─────────────────────────── cluster_topics ───────────────────────────

def test_cluster_topics_separates_distinct_groups():
    """Two well-separated clusters in 2D must yield 2 topics."""
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[0, 0], scale=0.01, size=(20, 2)).astype(np.float32)
    b = rng.normal(loc=[10, 10], scale=0.01, size=(20, 2)).astype(np.float32)
    emb = np.vstack([a, b])
    labels, n = cluster_topics(emb, over_k=4, merge_threshold=0.5)
    assert n == 2
    # Each input row got a label
    assert labels.shape == (40,)
    # The two halves should land in different topics
    assert len(set(labels[:20].tolist())) == 1
    assert len(set(labels[20:].tolist())) == 1
    assert labels[0] != labels[20]


def test_cluster_topics_empty_input():
    labels, n = cluster_topics(np.zeros((0, 4), dtype=np.float32))
    assert n == 0
    assert labels.size == 0


def test_cluster_topics_single_row():
    emb = np.array([[1.0, 2.0]], dtype=np.float32)
    labels, n = cluster_topics(emb, over_k=24)
    assert n == 1
    assert labels.tolist() == [0]


# ───────────────────────── pick_representatives ─────────────────────────

def test_pick_reps_returns_nearest_to_centroid():
    # 4 points: 3 near (0,0), 1 far at (100,100)
    emb = np.array([
        [0.0, 0.0], [0.1, 0.0], [0.0, 0.1], [100.0, 100.0],
    ], dtype=np.float32)
    labels = np.array([0, 0, 0, 0])
    idx = pick_representatives(emb, labels, topic=0, k=2)
    # The far point (idx=3) must NOT be among top-2 nearest to centroid
    assert 3 not in idx.tolist()
    assert len(idx) == 2


def test_pick_reps_empty_topic_returns_empty():
    emb = np.array([[0.0, 0.0]], dtype=np.float32)
    labels = np.array([0])
    idx = pick_representatives(emb, labels, topic=99, k=5)
    assert idx.size == 0


# ───────────────────────────── run_selfsynth ─────────────────────────────

class _FakeCol:
    """Stub chromadb collection."""
    def __init__(self, emb=None, docs=None):
        self.emb = emb or []
        self.docs = docs or []
        self.upserts = []

    def get(self, include=None):
        return {"embeddings": self.emb, "documents": self.docs}

    def upsert(self, ids, embeddings, documents, metadatas):
        for i, d in zip(ids, documents):
            self.upserts.append((i, d))

    def count(self):
        return len(self.upserts)


def test_run_selfsynth_writes_to_vault_and_wiki_collection(tmp_path):
    """End-to-end with injected fakes: produces .md + upserts wiki rows
    + writes a graph.db file."""
    # Two well-separated clusters → 2 topics expected
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[0, 0, 0, 0], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    b = rng.normal(loc=[10, 10, 10, 10], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    docs = [f"doc_a_{i}" for i in range(10)] + [f"doc_b_{i}" for i in range(10)]
    source = _FakeCol(emb=a + b, docs=docs)
    wiki = _FakeCol()

    embed_calls = []
    def fake_embed(text):
        embed_calls.append(text)
        return [0.0, 0.0, 0.0, 0.0]
    def fake_llm(prompt):
        return f"SYNTHESIZED({prompt[:20]}…)"
    def fake_extract(text):
        return (["entityA", "entityB"], [("entityA", "rel", "entityB")])

    out = run_selfsynth(
        source_collection=source,
        wiki_collection=wiki,
        vault_dir=str(tmp_path / "vault"),
        embed_fn=fake_embed,
        llm_synth_fn=fake_llm,
        extractor_fn=fake_extract,
        graph_db_path=str(tmp_path / "graph.db"),
        slug_prefix="test",
        over_k=4,
        merge_threshold=0.5,
        reps_per_topic=3,
        updated="2026-06-26",
    )
    assert out["topics"] == 2
    assert out["wikis_made"] == 2
    assert out["wiki_count"] == 2
    # Vault file present
    md_files = list((tmp_path / "vault").rglob("*.md"))
    assert len(md_files) == 2
    # Wiki collection received both upserts
    assert {u[0] for u in wiki.upserts} == {"test_00", "test_01"}
    # Embedder was called per-upsert
    assert len(embed_calls) == 2
    # graph.db created
    assert (tmp_path / "graph.db").exists()


def test_run_selfsynth_regraphs_when_topic_content_changes(tmp_path):
    """Re-running over the same vault/graph with the SAME topic slugs but
    evolved entities must still update the relation graph.

    Topic slugs (`<prefix>_00`) are reused on every batch, so keying the
    graph unit_id on the slug alone makes `is_processed` skip every topic
    from the second run onward — the graph freezes at its first snapshot
    even as the underlying memory grows.
    """
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[0, 0, 0, 0], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    b = rng.normal(loc=[10, 10, 10, 10], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    docs = [f"doc_{i}" for i in range(20)]
    graph_db = str(tmp_path / "graph.db")

    def _run(extract):
        return run_selfsynth(
            source_collection=_FakeCol(emb=a + b, docs=docs),
            wiki_collection=_FakeCol(),
            vault_dir=str(tmp_path / "vault"),
            embed_fn=lambda t: [0.0],
            llm_synth_fn=lambda p: "body",
            extractor_fn=extract,
            graph_db_path=graph_db,
            slug_prefix="test", over_k=4, merge_threshold=0.5, reps_per_topic=3,
        )

    first = _run(lambda t: (["alpha", "beta"], [("alpha", "rel", "beta")]))
    assert first["nodes"] == 2

    # Same slugs, evolved content → must be re-graphed, not skipped
    second = _run(lambda t: (["alpha", "beta", "gamma", "delta"], []))
    assert second["nodes"] > first["nodes"], (
        "relation graph frozen: re-synthesized topics were skipped as "
        "already-processed because unit_id ignores content")


def test_run_selfsynth_identical_rerun_stays_idempotent(tmp_path):
    """Guard the other direction: an unchanged re-run must NOT double-count.
    Same entities → same unit_id → skipped, node count unchanged."""
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[0, 0, 0, 0], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    b = rng.normal(loc=[10, 10, 10, 10], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    docs = [f"doc_{i}" for i in range(20)]
    graph_db = str(tmp_path / "graph.db")
    same = lambda t: (["alpha", "beta"], [("alpha", "rel", "beta")])

    def _run():
        return run_selfsynth(
            source_collection=_FakeCol(emb=a + b, docs=docs),
            wiki_collection=_FakeCol(),
            vault_dir=str(tmp_path / "vault"),
            embed_fn=lambda t: [0.0],
            llm_synth_fn=lambda p: "body",
            extractor_fn=same,
            graph_db_path=graph_db,
            slug_prefix="test", over_k=4, merge_threshold=0.5, reps_per_topic=3,
        )

    first = _run()
    second = _run()
    assert second["nodes"] == first["nodes"]
    assert second["edges"] == first["edges"]


def test_run_selfsynth_empty_source_returns_zero(tmp_path):
    """No source rows → no wikis, no errors."""
    source = _FakeCol(emb=[], docs=[])
    wiki = _FakeCol()
    out = run_selfsynth(
        source_collection=source,
        wiki_collection=wiki,
        vault_dir=str(tmp_path / "vault"),
        embed_fn=lambda t: [0.0],
        llm_synth_fn=lambda p: "x",
        extractor_fn=lambda t: ([], []),
        graph_db_path=str(tmp_path / "graph.db"),
    )
    assert out == {"topics": 0, "wikis_made": 0, "wiki_count": 0,
                   "nodes": 0, "edges": 0, "log": out["log"]}


def test_run_selfsynth_empty_llm_body_is_skipped(tmp_path):
    """If LLM returns "" the WikiStore.upsert short-circuits (returns "")
    and that topic is not counted as made/indexed."""
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[0, 0, 0, 0], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    b = rng.normal(loc=[10, 10, 10, 10], scale=0.01, size=(10, 4)).astype(np.float32).tolist()
    docs = [f"doc_a_{i}" for i in range(10)] + [f"doc_b_{i}" for i in range(10)]
    source = _FakeCol(emb=a + b, docs=docs)
    wiki = _FakeCol()
    out = run_selfsynth(
        source_collection=source,
        wiki_collection=wiki,
        vault_dir=str(tmp_path / "vault"),
        embed_fn=lambda t: [0.0],
        llm_synth_fn=lambda p: "",          # always empty
        extractor_fn=lambda t: ([], []),
        graph_db_path=str(tmp_path / "graph.db"),
        over_k=4, merge_threshold=0.5, reps_per_topic=3,
    )
    assert out["topics"] == 2
    assert out["wikis_made"] == 0          # nothing actually synthesized
    assert out["wiki_count"] == 0          # nothing reached wiki collection
