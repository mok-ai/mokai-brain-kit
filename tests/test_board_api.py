import json

import pytest

from brain_share.board_api import BoardSettings, board_settings, handle
from brain_share.task_board import TaskBoard

KEY = "board-key"
OK = {"X-Brain-Board-Key": KEY, "Content-Type": "application/json"}


@pytest.fixture
def board(tmp_path):
    b = TaskBoard(tmp_path / "task_board.db")
    yield b
    b.close()


def settings(**kw):
    return BoardSettings(**{"key": KEY, "owner": "대표", **kw})


def call(board, method, path, body=None, headers=OK, cfg=None):
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    return handle(board, cfg or settings(), method, path, headers, raw)


# ───────────────────────────── auth ─────────────────────────────────

def test_disabled_board_returns_503_with_reason(board):
    st, p = call(board, "GET", "/api/tasks",
                 cfg=BoardSettings(error="키 없음"))
    assert st == 503 and p["error"] == "키 없음"


@pytest.mark.parametrize("headers", [{}, {"X-Brain-Board-Key": "nope"},
                                     {"X-Brain-Board-Key": KEY + "x"}])
def test_wrong_or_missing_key_is_401(board, headers):
    st, _ = call(board, "GET", "/api/tasks", headers=headers)
    assert st == 401


def test_post_requires_json_content_type(board):
    st, _ = call(board, "POST", "/api/tasks", {"title": "x"},
                 headers={"X-Brain-Board-Key": KEY,
                          "Content-Type": "text/plain"})
    assert st == 415
    assert board.list() == []


def test_bad_json_and_non_object(board):
    st, _ = handle(board, settings(), "POST", "/api/tasks", OK, b"{nope")
    assert st == 400
    st, _ = handle(board, settings(), "POST", "/api/tasks", OK, b"[1]")
    assert st == 400


def test_oversized_body_is_413(board):
    st, _ = handle(board, settings(), "POST", "/api/tasks", OK,
                   b"{" + b" " * (64 * 1024 + 1) + b"}")
    assert st == 413


# ───────────────────────────── routes ───────────────────────────────

def test_create_uses_owner_as_requester_and_lists(board):
    st, t = call(board, "POST", "/api/tasks",
                 {"title": "보고서", "assignee": "김비서", "priority": "high",
                  "due": "2026-10-01", "requester": "spoofed"})
    assert st == 201
    assert t["requester"] == "대표"  # not taken from the body
    st, d = call(board, "GET", "/api/tasks")
    assert st == 200
    assert [x["title"] for x in d["tasks"]] == ["보고서"]
    assert d["summary"]["counts"]["pending"] == 1
    assert d["owner"] == "대표"


def test_validation_errors_are_409_with_message(board):
    st, p = call(board, "POST", "/api/tasks", {"title": ""})
    assert st == 409 and "제목" in p["error"]


def test_get_one_and_404s(board):
    board.create("x", requester="대표")
    assert call(board, "GET", "/api/tasks/1")[0] == 200
    assert call(board, "GET", "/api/tasks/9")[0] == 404
    assert call(board, "GET", "/api/tasks/abc")[0] == 404
    assert call(board, "POST", "/api/tasks/1/explode", {})[0] == 404
    assert call(board, "GET", "/api/tasks/1/approve")[0] == 405
    assert call(board, "POST", "/api/tasks/1", {})[0] == 405
    assert call(board, "DELETE", "/api/tasks")[0] == 405


def test_owner_actions_through_the_api(board):
    t = board.create("x", requester="대표")
    assert call(board, "POST", "/api/tasks/1/assign",
                {"assignee": "김비서"})[1]["assignee"] == "김비서"
    board.claim(t["id"], agent="김비서")
    assert call(board, "POST", "/api/tasks/1/block",
                {"reason": "권한"})[1]["status"] == "blocked"
    assert call(board, "POST", "/api/tasks/1/unblock",
                {})[1]["status"] == "in_progress"
    board.report(t["id"], agent="김비서", summary="끝")
    st, p = call(board, "POST", "/api/tasks/1/reject", {"reason": ""})
    assert st == 409
    assert call(board, "POST", "/api/tasks/1/reject",
                {"reason": "보완"})[1]["status"] == "in_progress"
    board.report(t["id"], agent="김비서", summary="보완함")
    st, done = call(board, "POST", "/api/tasks/1/approve", {"note": "OK"})
    assert st == 200 and done["status"] == "done"
    assert "wiki_path" not in done  # no vault configured
    st, c = call(board, "POST", "/api/tasks/1/comment", {"text": "수고"})
    assert c["events"][-1]["actor"] == "대표"


def test_approve_exports_to_vault_when_configured(board, tmp_path):
    t = board.create("x", requester="대표", division="TECH")
    board.claim(t["id"], agent="a")
    board.report(t["id"], agent="a", summary="s")
    st, p = call(board, "POST", "/api/tasks/1/approve", {},
                 cfg=settings(vault_dir=str(tmp_path / "vault")))
    assert st == 200
    assert (tmp_path / "vault" / "TECH" / "task_00001.md").exists()
    assert p["wiki_path"].endswith("task_00001.md")


def test_approve_stands_even_if_export_fails(board, tmp_path):
    t = board.create("x", requester="대표")
    board.claim(t["id"], agent="a")
    board.report(t["id"], agent="a", summary="s")
    blocker = tmp_path / "file"
    blocker.write_text("not a dir")
    st, p = call(board, "POST", "/api/tasks/1/approve", {},
                 cfg=settings(vault_dir=str(blocker)))
    assert st == 200 and p["status"] == "done"
    assert p["export_error"]


# ───────────────────────────── settings ─────────────────────────────

def write_cfg(root, d):
    (root / "brain_share_config.json").write_text(json.dumps(d),
                                                  encoding="utf-8")


def test_settings_from_config_and_env(tmp_path):
    write_cfg(tmp_path, {"read_key": "rk", "board": {"key": "bk",
                                                     "owner": "목대표"}})
    s = board_settings(tmp_path, env={})
    assert (s.key, s.owner, s.error) == ("bk", "목대표", "")
    write_cfg(tmp_path, {"read_key": "rk"})
    s = board_settings(tmp_path, env={"BRAIN_BOARD_KEY": "ek"})
    assert (s.key, s.owner) == ("ek", "대표")


def test_settings_without_key_disable_board(tmp_path):
    s = board_settings(tmp_path, env={})
    assert not s.key and "보드 키" in s.error


@pytest.mark.parametrize("cfg,needle", [
    ({"read_key": "same", "board": {"key": "same"}}, "read_key"),
    ({"read_key": "rk", "desk": {"key": "same"}, "board": {"key": "same"}},
     "desk"),
])
def test_settings_refuse_shared_keys(tmp_path, cfg, needle):
    write_cfg(tmp_path, cfg)
    s = board_settings(tmp_path, env={})
    assert not s.key and needle in s.error


def test_settings_survive_broken_config(tmp_path):
    (tmp_path / "brain_share_config.json").write_text("{nope",
                                                      encoding="utf-8")
    s = board_settings(tmp_path, env={})
    assert s.error and not s.key
