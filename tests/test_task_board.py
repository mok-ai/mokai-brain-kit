import sqlite3

import pytest

from brain_share.config import BrainShareConfig
from brain_share.task_board import (
    TaskBoard,
    TaskError,
    TaskNotFound,
    export_to_vault,
    is_private,
    read_summary,
    to_task_record,
)
from brain_share.wiki_page import parse_page


@pytest.fixture
def board(tmp_path):
    t = [1790000000.0]

    def clock():
        t[0] += 1
        return t[0]

    b = TaskBoard(tmp_path / "task_board.db", clock=clock)
    yield b
    b.close()


def kinds(task):
    return [e["kind"] for e in task["events"]]


# ───────────────────────────── create / read ─────────────────────────

def test_create_defaults_and_history(board):
    t = board.create("분기 보고서 초안", requester="대표", assignee="김비서",
                     priority="high", due="2026-10-01")
    assert t["id"] == 1
    assert t["status"] == "pending"
    assert t["assignee"] == "김비서"
    assert t["priority"] == "high"
    assert kinds(t) == ["created"]
    assert t["events"][0]["actor"] == "대표"


@pytest.mark.parametrize("kw,msg", [
    ({"title": ""}, "제목"),
    ({"title": "x" * 201}, "제목"),
    ({"requester": ""}, "요청자"),
    ({"priority": "asap"}, "우선순위"),
    ({"due": "10/01/2026"}, "YYYY-MM-DD"),
    ({"due": "2026-02-30"}, "날짜"),
])
def test_create_rejects_bad_input(board, kw, msg):
    args = {"title": "t", "requester": "대표"}
    args.update(kw)
    title = args.pop("title")
    with pytest.raises(TaskError, match=msg):
        board.create(title, **args)
    assert board.list() == []


def test_list_orders_by_priority_then_due(board):
    board.create("low", requester="대표", priority="low")
    board.create("normal-late", requester="대표", due="2026-12-01")
    board.create("normal-early", requester="대표", due="2026-10-01")
    board.create("urgent", requester="대표", priority="urgent")
    board.create("normal-nodue", requester="대표")
    assert [t["title"] for t in board.list()] == [
        "urgent", "normal-early", "normal-late", "normal-nodue", "low"]


def test_list_filters(board):
    board.create("a", requester="대표", assignee="김비서")
    b = board.create("b", requester="대표")
    board.claim(b["id"], agent="leaf1")
    assert [t["title"] for t in board.list(assignee="김비서")] == ["a"]
    assert [t["title"] for t in board.list(status="in_progress")] == ["b"]
    with pytest.raises(TaskError):
        board.list(status="nope")


def test_get_unknown_raises_not_found(board):
    with pytest.raises(TaskNotFound):
        board.get(99)
    with pytest.raises(TaskNotFound):
        board.get("abc")


# ───────────────────────────── the full flow ─────────────────────────

def test_happy_path_request_claim_report_approve(board):
    t = board.create("위키 정리", requester="대표")
    t = board.claim(t["id"], agent="김비서")
    assert (t["status"], t["assignee"]) == ("in_progress", "김비서")
    t = board.report(t["id"], agent="김비서", summary="중복 12건 병합",
                     outputs=["report.md"], lessons="링크는 파일명도 인정")
    assert t["status"] == "review"
    assert t["outputs"] == ["report.md"]
    t = board.approve(t["id"], actor="대표", note="좋아요")
    assert t["status"] == "done"
    assert kinds(t) == ["created", "claimed", "reported", "approved"]


def test_reject_sends_back_with_reason(board):
    t = board.create("x", requester="대표", assignee="김비서")
    board.claim(t["id"], agent="김비서")
    board.report(t["id"], agent="김비서", summary="done")
    with pytest.raises(TaskError, match="사유"):
        board.reject(t["id"], actor="대표", reason="  ")
    t = board.reject(t["id"], actor="대표", reason="근거 자료 추가")
    assert t["status"] == "in_progress"
    assert t["events"][-1]["text"] == "근거 자료 추가"
    # can report again after a rejection
    t = board.report(t["id"], agent="김비서", summary="근거 추가함")
    assert t["status"] == "review"


def test_block_and_unblock(board):
    t = board.create("x", requester="대표")
    board.claim(t["id"], agent="a")
    t = board.block(t["id"], actor="a", reason="API 키 필요")
    assert t["status"] == "blocked"
    t = board.unblock(t["id"], actor="대표", note="키 전달함")
    assert t["status"] == "in_progress"


@pytest.mark.parametrize("action", ["report", "approve", "reject", "block",
                                    "unblock"])
def test_illegal_transitions_from_pending(board, action):
    t = board.create("x", requester="대표")
    call = {
        "report": lambda: board.report(t["id"], agent="a", summary="s"),
        "approve": lambda: board.approve(t["id"], actor="대표"),
        "reject": lambda: board.reject(t["id"], actor="대표", reason="r"),
        "block": lambda: board.block(t["id"], actor="a", reason="r"),
        "unblock": lambda: board.unblock(t["id"], actor="a"),
    }[action]
    with pytest.raises(TaskError):
        call()
    assert board.get(t["id"])["status"] == "pending"
    assert kinds(board.get(t["id"])) == ["created"]


def test_cannot_approve_twice(board):
    t = board.create("x", requester="대표")
    board.claim(t["id"], agent="a")
    board.report(t["id"], agent="a", summary="s")
    board.approve(t["id"], actor="대표")
    with pytest.raises(TaskError, match="완료"):
        board.approve(t["id"], actor="대표")


def test_claim_respects_existing_assignee(board):
    t = board.create("x", requester="대표", assignee="김비서")
    with pytest.raises(TaskError, match="김비서"):
        board.claim(t["id"], agent="leaf1")
    assert board.claim(t["id"], agent="김비서")["status"] == "in_progress"


def test_second_claim_loses(board):
    t = board.create("x", requester="대표")
    board.claim(t["id"], agent="a")
    with pytest.raises(TaskError):
        board.claim(t["id"], agent="b")
    assert board.get(t["id"])["assignee"] == "a"


def test_only_assignee_can_report(board):
    t = board.create("x", requester="대표")
    board.claim(t["id"], agent="a")
    with pytest.raises(TaskError, match="담당자"):
        board.report(t["id"], agent="b", summary="mine now")
    assert board.get(t["id"])["status"] == "in_progress"


def test_assign_and_comment(board):
    t = board.create("x", requester="대표")
    t = board.assign(t["id"], "leaf2", actor="대표")
    assert t["assignee"] == "leaf2"
    t = board.comment(t["id"], actor="leaf2", text="내일 착수")
    assert t["events"][-1] == {**t["events"][-1], "kind": "commented",
                               "actor": "leaf2", "text": "내일 착수"}
    with pytest.raises(TaskError):
        board.comment(t["id"], actor="leaf2", text="")


def test_failed_write_leaves_no_partial_history(board, monkeypatch):
    t = board.create("x", requester="대표")
    real = board._conn

    class Boom:
        def __init__(self):
            self.n = 0

        def execute(self, sql, *a):
            if sql.startswith("INSERT INTO events"):
                raise sqlite3.OperationalError("disk full")
            return real.execute(sql, *a)

    board._conn = Boom()
    with pytest.raises(sqlite3.OperationalError):
        board.claim(t["id"], agent="a")
    board._conn = real
    after = board.get(t["id"])
    assert after["status"] == "pending"
    assert after["assignee"] == ""


# ───────────────────────────── summary ───────────────────────────────

def test_summary_counts_and_overdue(board, tmp_path):
    a = board.create("a", requester="대표", due="2026-01-01")
    board.create("b", requester="대표", due="2099-01-01")
    c = board.create("c", requester="대표", due="2026-01-01")
    board.claim(a["id"], agent="x")
    board.report(a["id"], agent="x", summary="s")
    board.claim(c["id"], agent="y")
    board.report(c["id"], agent="y", summary="s")
    board.approve(c["id"], actor="대표")  # done tasks are never overdue
    s = board.summary(today="2026-09-27")
    assert s["counts"] == {"pending": 1, "in_progress": 0, "blocked": 0,
                           "review": 1, "done": 1}
    assert s["awaiting_approval"] == 1
    assert s["overdue"] == 1
    assert s["total"] == 3
    assert read_summary(tmp_path / "task_board.db")["total"] == 3


def test_read_summary_does_not_create_db(tmp_path):
    assert read_summary(tmp_path / "missing.db") is None
    assert not (tmp_path / "missing.db").exists()


# ───────────────────────────── privacy / export ──────────────────────

def test_is_private():
    cfg = BrainShareConfig(blocked_divisions=["ACCOUNTING"])
    assert is_private({"division": "ACCOUNTING"}, cfg)
    assert is_private({"sensitivity": "secret"}, cfg)
    assert not is_private({"division": "TECH", "sensitivity": "internal"}, cfg)
    assert not is_private({"division": "", "sensitivity": "internal"}, cfg)


def test_export_approved_task_to_vault(board, tmp_path):
    t = board.create("회의록/요약 자동화", requester="대표", division="TECH")
    board.claim(t["id"], agent="a")
    board.report(t["id"], agent="a", summary="스크립트 완성",
                 outputs=["summarize.py"], lessons="화자 분리 필요")
    with pytest.raises(TaskError):
        export_to_vault(board.get(t["id"]), tmp_path / "vault")
    board.approve(t["id"], actor="대표")
    path = export_to_vault(board.get(t["id"]), tmp_path / "vault")
    # A "/" in the title must not become a directory.
    assert path.endswith("TECH/task_00001.md") or \
        path.endswith("TECH\\task_00001.md")
    page = parse_page(open(path, encoding="utf-8").read())
    assert page.namespace == "TECH"
    assert "summarize.py" in page.body
    assert "스크립트 완성" in page.body
    assert "화자 분리 필요" in page.body


def test_to_task_record_maps_review_to_in_progress(board):
    t = board.create("x", requester="대표")
    board.claim(t["id"], agent="a")
    board.report(t["id"], agent="a", summary="s")
    assert to_task_record(board.get(t["id"])).status == "in_progress"
