from brain_share.wiki_synth import synthesize_topic


def fake_llm(prompt):
    return "# 정본\n합성된 정본 본문. 모순 해소 완료."


def fake_extractor(text):
    return (["project_x"], [{"from": "project_x", "type": "about", "to": "wiki"}])


def chunks():
    return [{"id": "rag_a", "content": "조각 A"}, {"id": "rag_b", "content": "조각 B"}]


def test_synthesize_builds_page():
    page = synthesize_topic("project_x", "TECH", chunks(), "2026-06-21",
                            fake_llm, fake_extractor)
    assert page.topic == "project_x" and page.namespace == "TECH"
    assert page.sources == ["rag_a", "rag_b"]
    assert page.promote == "pending"
    assert "합성된 정본 본문" in page.body
    assert page.entities == ["project_x"]
    assert page.relations[0]["type"] == "about"
    assert page.sensitivity == "internal"
    assert page.updated == "2026-06-21"


def test_synthesize_empty_chunks():
    called = []
    def spy_llm(p): called.append(p); return ""
    page = synthesize_topic("t", "TECH", [], "2026-06-21", spy_llm, fake_extractor)
    assert page.sources == [] and page.body == ""
    assert called == [], "llm_fn must not be called on empty chunks"
