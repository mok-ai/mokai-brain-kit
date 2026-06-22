from brain_share.entity_extractor import extract_entities, backlinks

def fake_llm_ok(prompt):
    return '여기 결과: {"entities":["project_x","MAIN_PC"],"relations":[{"from":"project_x","type":"affects","to":"MAIN_PC"}]} 끝'

def fake_llm_garbage(prompt):
    return "관계를 못 찾았습니다."

def test_extract_parses_embedded_json():
    ents, rels = extract_entities("프로젝트 X는 메인 PC에 영향", fake_llm_ok)
    assert ents == ["project_x", "MAIN_PC"]
    assert rels[0] == {"from": "project_x", "type": "affects", "to": "MAIN_PC"}

def test_extract_garbage_returns_empty():
    assert extract_entities("아무거나", fake_llm_garbage) == ([], [])

def test_backlinks_intersect_and_format():
    out = backlinks(["project_x", "UNKNOWN", "MAIN_PC"], {"project_x", "MAIN_PC", "other"})
    assert out == ["[[MAIN_PC]]", "[[project_x]]"]

def test_extract_llm_returns_none():
    assert extract_entities("x", lambda p: None) == ([], [])

def test_extract_llm_returns_empty_string():
    assert extract_entities("x", lambda p: "") == ([], [])

def test_relation_with_extra_keys_is_kept():
    def llm(p):
        return '{"entities":["a"],"relations":[{"from":"a","type":"owns","to":"b","weight":5}]}'
    ents, rels = extract_entities("x", llm)
    assert rels[0]["from"] == "a" and rels[0]["weight"] == 5
