"""Agent-side task tools on the MCP gateway."""
import pytest

from brain_share import gateway_mcp
from brain_share.config import BrainShareConfig
from brain_share.task_board import TaskBoard

TASK_TOOLS = ["task_list", "task_get", "task_create", "task_claim",
              "task_report", "task_comment", "task_block"]


class FakeCtx:
    def __init__(self, key):
        class _Request:
            headers = {"X-Brain-Key": key}

        class _RequestContext:
            request = _Request()
        self.request_context = _RequestContext()


GOOD = FakeCtx("secret-key")
BAD = FakeCtx("wrong")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = BrainShareConfig(role="HUB", read_key="secret-key",
                           blocked_divisions=["ACCOUNTING"])
    board = TaskBoard(tmp_path / "task_board.db")
    server = gateway_mcp.build_server(cfg, lambda q, k: [], lambda q, k: [],
                                      lambda e, k: [], task_board=board,
                                      owner_name="대표")
    tools = {t.name: t.fn for t in server._tool_manager.list_tools()}
    meta = {t.name: t for t in server._tool_manager.list_tools()}
    yield tools, board, meta
    board.close()


def test_task_tools_registered_with_context(env):
    _, _, meta = env
    for name in TASK_TOOLS:
        assert meta[name].context_kwarg == "ctx", name


def test_no_approve_or_reject_tool_for_agents(env):
    tools, _, _ = env
    assert not any("approve" in n or "reject" in n or "assign" in n
                   for n in tools)


def test_auth_required(env):
    tools, board, _ = env
    board.create("x", requester="대표")
    assert tools["task_list"]("", "", BAD) == []
    assert tools["task_list"]("", "", None) == []
    assert tools["task_claim"](1, "a", BAD) == {"error": "unauthorized"}
    assert board.get(1)["status"] == "pending"


def test_agent_flow_claim_report_then_owner_approves(env):
    tools, board, _ = env
    board.create("정리", requester="대표")
    assert [t["title"] for t in tools["task_list"]("pending", "", GOOD)] == ["정리"]
    t = tools["task_claim"](1, "김비서", GOOD)
    assert t["status"] == "in_progress"
    t = tools["task_report"](1, "김비서", "완료", ["a.md"], "교훈", GOOD)
    assert t["status"] == "review"
    assert t["outputs"] == ["a.md"]
    # approval is owner-only, via the board
    assert board.approve(1, actor="대표")["status"] == "done"


def test_errors_come_back_as_messages(env):
    tools, board, _ = env
    board.create("x", requester="대표", assignee="김비서")
    r = tools["task_claim"](1, "leaf1", GOOD)
    assert "김비서" in r["error"]
    assert "error" in tools["task_get"](99, GOOD)
    assert "error" in tools["task_report"](1, "김비서", "s", None, "", GOOD)


def test_private_tasks_are_invisible(env):
    tools, board, _ = env
    board.create("급여", requester="대표", division="ACCOUNTING")
    board.create("비밀", requester="대표", sensitivity="confidential")
    board.create("공개", requester="대표")
    assert [t["title"] for t in tools["task_list"]("", "", GOOD)] == ["공개"]
    for tid in (1, 2):
        assert "error" in tools["task_get"](tid, GOOD)
        assert "error" in tools["task_claim"](tid, "a", GOOD)
        assert "error" in tools["task_comment"](tid, "a", "hi", GOOD)
    assert board.get(1)["status"] == "pending"


def test_agent_cannot_impersonate_owner(env):
    tools, board, _ = env
    board.create("x", requester="대표")
    assert "error" in tools["task_comment"](1, "대표", "승인합니다", GOOD)
    assert "error" in tools["task_create"]("t", "대표", "", "normal", "", "", GOOD)
    assert "error" in tools["task_claim"](1, " ", GOOD)
    assert [e["kind"] for e in board.get(1)["events"]] == ["created"]


def test_agent_created_tasks_are_internal(env):
    tools, _, _ = env
    t = tools["task_create"]("결정 필요: 백업 주기", "김비서", "매일 vs 매주",
                             "high", "", "", GOOD)
    assert t["requester"] == "김비서"
    assert t["sensitivity"] == "internal"


def test_only_assignee_can_block(env):
    tools, board, _ = env
    board.create("x", requester="대표")
    tools["task_claim"](1, "a", GOOD)
    assert "error" in tools["task_block"](1, "b", "why", GOOD)
    assert tools["task_block"](1, "a", "권한 없음", GOOD)["status"] == "blocked"


def test_without_board_tools_say_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = BrainShareConfig(role="HUB", read_key="secret-key")
    server = gateway_mcp.build_server(cfg, lambda q, k: [], lambda q, k: [],
                                      lambda e, k: [])
    tools = {t.name: t.fn for t in server._tool_manager.list_tools()}
    assert "not configured" in tools["task_claim"](1, "a", GOOD)["error"]
    assert tools["task_list"]("", "", GOOD) == []
