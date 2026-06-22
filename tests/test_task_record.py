import pytest
from brain_share.task_record import TaskRecord, validate, to_wiki_page, VALID_STATUS
from brain_share.wiki_page import WikiPage

def rec(**kw):
    base = dict(task="MCP 게이트웨이 구현", status="done",
                outputs=["brain_share/gateway_core.py"], links=["project_x", "MAIN_PC"],
                lessons="필터는 드롭 우선이어야 안전", division="TECH",
                sensitivity="internal", updated="2026-06-21")
    base.update(kw); return TaskRecord(**base)

def test_validate_ok():
    validate(rec())  # no raise

def test_validate_bad_status():
    with pytest.raises(ValueError):
        validate(rec(status="finished"))

def test_validate_empty_task():
    with pytest.raises(ValueError):
        validate(rec(task=""))

def test_to_wiki_page_maps_fields():
    page = to_wiki_page(rec())
    assert isinstance(page, WikiPage)
    assert page.namespace == "TECH"
    assert page.entities == ["project_x", "MAIN_PC"]
    assert "필터는 드롭 우선" in page.body
    assert "done" in page.body

def test_to_wiki_page_rejects_invalid():
    with pytest.raises(ValueError):
        to_wiki_page(rec(status="invalid"))
