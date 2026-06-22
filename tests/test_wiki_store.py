from brain_share.wiki_store import WikiStore
from brain_share.wiki_page import WikiPage

class FakeIndexer:
    def __init__(self): self.docs = {}
    def upsert(self, id, text, metadata): self.docs[id] = (text, metadata)
    def search(self, query, top_k):
        return [{"id": k, "content": v[0], "metadata": v[1], "score": 0.9, "collection": "x"}
                for k, v in list(self.docs.items())[:top_k]]

def page(topic="project_x", body="정본 본문"):
    return WikiPage(topic=topic, namespace="TECH", updated="2026-06-21", body=body)

def test_upsert_writes_file_and_indexes(tmp_path):
    idx = FakeIndexer()
    store = WikiStore(str(tmp_path), idx)
    path = store.upsert(page())
    assert path.endswith("TECH/project_x.md") or path.endswith("TECH\\project_x.md")
    saved = open(path, encoding="utf-8").read()
    assert "정본 본문" in saved and saved.startswith("---")
    assert "project_x" in idx.docs

def test_empty_body_not_saved(tmp_path):
    idx = FakeIndexer()
    store = WikiStore(str(tmp_path), idx)
    assert store.upsert(page(body="")) == ""
    assert idx.docs == {}

def test_search_marks_collection_wiki(tmp_path):
    idx = FakeIndexer(); store = WikiStore(str(tmp_path), idx)
    store.upsert(page())
    out = store.search("project", 5)
    assert out and out[0]["collection"] == "wiki"

def test_whitespace_body_not_saved(tmp_path):
    idx = FakeIndexer()
    store = WikiStore(str(tmp_path), idx)
    assert store.upsert(page(body="   \n")) == ""
    assert idx.docs == {}
