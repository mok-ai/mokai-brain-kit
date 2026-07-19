import pytest
from brain_share.wiki_search import search_wiki, merge_and_dedupe


class _FakeCol:
    def __init__(self, docs, embs, ids, metas):
        self.docs = docs; self.embs = embs; self.ids = ids; self.metas = metas
    def query(self, query_embeddings, n_results, include=None):
        # simple: return all in stored order (test picks top_k)
        return {
            "ids": [self.ids[:n_results]],
            "documents": [self.docs[:n_results]],
            "distances": [[0.1 * (i+1) for i in range(min(n_results, len(self.ids)))]],
            "metadatas": [self.metas[:n_results]],
        }


class _FakeClient:
    def __init__(self, col): self._col = col
    def get_collection(self, name): return self._col


def _fake_embed(text): return [0.1, 0.2, 0.3, 0.4]


def test_search_wiki_returns_ranked_results_with_wiki_collection_tag():
    col = _FakeCol(
        docs=["alpha body", "beta body"],
        embs=[], ids=["kim_topic_00", "kim_topic_01"],
        metas=[{"division":"MEMORY","topic":"조이듀"}, {"division":"MEMORY","topic":"운영"}])
    def _client_factory(path): return _FakeClient(col)
    out = search_wiki("조이듀 운영", top_k=2,
                     chroma_path="ignored", collection_name="kim_wiki",
                     embedder_fn=_fake_embed, client_factory=_client_factory)
    assert len(out) == 2
    assert out[0]["id"] == "kim_topic_00"
    assert out[0]["collection"] == "wiki"
    assert 0.9 < out[0]["score"] <= 1.0  # from distance 0.1
    assert out[0]["content"] == "alpha body"
    assert out[0]["metadata"]["division"] == "MEMORY"


def test_search_wiki_empty_collection_returns_empty():
    col = _FakeCol(docs=[], embs=[], ids=[], metas=[])
    def _client_factory(path): return _FakeClient(col)
    out = search_wiki("q", top_k=5, chroma_path="ignored",
                     collection_name="anything_wiki",
                     embedder_fn=_fake_embed, client_factory=_client_factory)
    assert out == []


def test_search_wiki_missing_collection_swallowed_returns_empty():
    class _MissingClient:
        def get_collection(self, name): raise Exception("no such collection")
    def _factory(path): return _MissingClient()
    out = search_wiki("q", top_k=5, chroma_path="ignored",
                     collection_name="ghost_wiki",
                     embedder_fn=_fake_embed, client_factory=_factory)
    assert out == []


def test_merge_and_dedupe_wiki_first_then_rag():
    primary = [{"id":"w1","score":0.9,"content":"w1","collection":"wiki","metadata":{}}]
    secondary = [{"id":"w1","score":0.5,"content":"dup","collection":"knowledge","metadata":{}},
                 {"id":"r1","score":0.8,"content":"r1","collection":"knowledge","metadata":{}}]
    out = merge_and_dedupe(primary, secondary, top_k=5)
    assert [r["id"] for r in out] == ["w1", "r1"]
    assert out[0]["content"] == "w1"  # primary body kept, not secondary dup


def test_merge_and_dedupe_respects_top_k():
    primary = [{"id":f"w{i}","score":1.0,"content":"","collection":"wiki","metadata":{}} for i in range(3)]
    secondary = [{"id":f"r{i}","score":0.5,"content":"","collection":"knowledge","metadata":{}} for i in range(5)]
    out = merge_and_dedupe(primary, secondary, top_k=4)
    assert len(out) == 4
    assert [r["id"] for r in out] == ["w0","w1","w2","r0"]


def test_search_wiki_embedder_fn_none_and_lazy_import_failure_returns_empty(monkeypatch):
    """When embedder_fn is None and lazy sentence-transformers import fails,
    the function must return [] instead of raising — so callers can fall
    back to RAG API gracefully."""
    import sys
    # Simulate a broken sentence-transformers by pointing to a nonexistent name
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    out = search_wiki("q", top_k=5, chroma_path="ignored",
                     collection_name="x_wiki",
                     embedder_fn=None,
                     client_factory=lambda p: _FakeClient(_FakeCol([],[],[],[])))
    assert out == []
