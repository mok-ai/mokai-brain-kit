from brain_share.wiki_page import WikiPage, render_page, parse_page

def sample():
    return WikiPage(
        topic="project_x", namespace="TECH", sensitivity="internal",
        updated="2026-06-21", sources=["rag_1", "rag_2"], promote="pending",
        entities=["project_x", "MAIN_PC"],
        relations=[{"from": "project_x", "type": "affects", "to": "MAIN_PC"}],
        body="# project_x\n\n정본 본문입니다.\n[[MAIN_PC]]\n",
    )

def test_render_has_frontmatter_and_body():
    md = render_page(sample())
    assert md.startswith("---\n")
    assert "topic: project_x" in md
    assert "정본 본문입니다." in md

def test_round_trip():
    page = sample()
    parsed = parse_page(render_page(page))
    assert parsed.topic == page.topic
    assert parsed.sensitivity == "internal"
    assert parsed.sources == ["rag_1", "rag_2"]
    assert parsed.relations[0]["type"] == "affects"
    assert "정본 본문입니다." in parsed.body
    assert parsed == page  # full field-by-field round-trip

def test_parse_without_frontmatter_is_body_only():
    p = parse_page("그냥 본문")
    assert p.body.strip() == "그냥 본문"
    assert p.topic == ""

def test_round_trip_body_with_horizontal_rule():
    page = WikiPage(topic="t", namespace="TECH", updated="2026-06-21",
                    body="intro\n---\nmore content\n")
    parsed = parse_page(render_page(page))
    assert parsed == page
    assert parsed.body == "intro\n---\nmore content\n"
