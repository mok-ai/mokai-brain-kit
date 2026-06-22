import sys
import types
import pytest
from brain_share.config import BrainShareConfig


def _install_fake_mm(rows):
    sys.modules.pop("brain_share.mm_adapter", None)
    calls = []

    class FakeWiki:
        def upsert(self, **kw):
            pass

    class FakeMM:
        def __init__(self):
            self.collections = {"wiki": FakeWiki()}

        def _embed_query(self, t):
            return [0.0]

        def search(self, query, collections=None, top_k=5):
            calls.append({"query": query, "collections": collections, "top_k": top_k})
            return list(rows)

    mod = types.ModuleType("memory_manager")
    mod.MemoryManager = FakeMM
    sys.modules["memory_manager"] = mod
    return calls


@pytest.fixture(autouse=True)
def cleanup_mm_adapter():
    yield
    # clean up so tests don't bleed
    sys.modules.pop("memory_manager", None)
    sys.modules.pop("brain_share.mm_adapter", None)


def cfg(tmp_path):
    return BrainShareConfig(
        role="HUB",
        read_key="k",
        blocked_divisions=["ACCT"],
        allowed_collections=["wiki", "knowledge"],
        vault_dir=str(tmp_path),
    )


def row(id, division="TECH", collection="knowledge"):
    return {
        "id": id,
        "content": "c",
        "score": 0.9,
        "collection": collection,
        "metadata": {"division": division},
    }


def test_wiki_search_restricts_to_wiki_collection(tmp_path):
    calls = _install_fake_mm([row("a", collection="wiki")])
    from brain_share.mm_adapter import make_backends

    wiki_search, rag_search, related_fn = make_backends(cfg(tmp_path))
    wiki_search("q", 3)
    assert any(c["collections"] == ["wiki"] for c in calls)


def test_rag_search_no_wiki_restriction(tmp_path):
    calls = _install_fake_mm([row("a")])
    from brain_share.mm_adapter import make_backends

    _, rag_search, _ = make_backends(cfg(tmp_path))
    rag_search("q", 3)
    assert any(c["collections"] is None and c["top_k"] == 3 for c in calls)


def test_related_fn_filters_blocked(tmp_path):
    _install_fake_mm([row("r1", division="ACCT"), row("r2")])
    from brain_share.mm_adapter import make_backends

    _, _, related_fn = make_backends(cfg(tmp_path))
    out = related_fn("e", 5)
    assert [r["id"] for r in out] == ["r2"]
