from brain_share.config import BrainShareConfig
from brain_share.sensitivity_filter import is_blocked, filter_results

def cfg():
    return BrainShareConfig(
        role="HUB", read_key="k", blocked_divisions=["ACCT", "TRADE"],
        blocked_tag_patterns=["회계", "고객명단"],
        blocked_keyword_patterns=["api_key", "비밀번호"],
        allowed_collections=["knowledge", "decisions"],
    )

def R(content="공개 지식", division="TECH", tags=None, collection="knowledge"):
    return {"id": "1", "content": content, "score": 0.9,
            "collection": collection, "metadata": {"division": division, "tags": tags or []}}

def test_public_passes():
    assert is_blocked(R(), cfg()) is False

def test_blocked_division():
    assert is_blocked(R(division="ACCT"), cfg()) is True

def test_blocked_tag_in_list():
    assert is_blocked(R(tags=["회계", "월보고"]), cfg()) is True

def test_blocked_tag_in_comma_string():
    assert is_blocked(R(tags="안내,고객명단,영업"), cfg()) is True

def test_blocked_keyword_in_content_caseless():
    assert is_blocked(R(content="설정에 API_KEY=abc 가 있음"), cfg()) is True

def test_collection_not_allowed():
    assert is_blocked(R(collection="conversations"), cfg()) is True

def test_filter_drops_only_blocked():
    rows = [R(), R(division="ACCT"), R(content="비밀번호 1234")]
    out = filter_results(rows, cfg())
    assert len(out) == 1 and out[0]["metadata"]["division"] == "TECH"

def test_empty_allowed_means_no_collection_filter():
    c = cfg(); c.allowed_collections = []
    assert is_blocked(R(collection="conversations"), c) is False

def test_missing_division_passes_other_rules():
    r = {"id": "1", "content": "공개 지식", "score": 0.9,
         "collection": "knowledge", "metadata": {}}
    assert is_blocked(r, cfg()) is False

def test_none_content_does_not_crash():
    r = {"id": "1", "content": None, "score": 0.9,
         "collection": "knowledge", "metadata": {"division": "TECH", "tags": []}}
    assert is_blocked(r, cfg()) is False

def test_none_metadata_does_not_crash():
    r = {"id": "1", "content": "공개", "score": 0.9,
         "collection": "knowledge", "metadata": None}
    assert is_blocked(r, cfg()) is False
