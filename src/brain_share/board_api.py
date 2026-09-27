"""HTTP API behind the local task board page (owner side).

Kept free of http.server so it is testable as a plain function:
handle(...) takes the request pieces and returns (status, payload).

Auth: every /api/tasks call needs `X-Brain-Board-Key`. That custom header
also means a browser will not send the request cross-site without a CORS
preflight, which this server never answers — so a random web page cannot
drive the board through the operator's browser even on 127.0.0.1.

The board key is the owner's (it can approve). It must differ from the
gateway read_key, which every leaf holds, and from the desk key.
"""
from __future__ import annotations

import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from brain_share.task_board import TaskBoard, TaskError, TaskNotFound, \
    export_to_vault

MAX_BODY = 64 * 1024
_TASK_PATH = re.compile(r"^/api/tasks/(\d+)(?:/([a-z]+))?$")


@dataclass
class BoardSettings:
    key: str = ""
    owner: str = "대표"
    vault_dir: str = ""
    error: str = ""  # why the board is disabled, shown on the page


def board_settings(root, env=None) -> BoardSettings:
    """Read `board` from <root>/brain_share_config.json (key may come from
    $BRAIN_BOARD_KEY). Never raises: a problem disables the board with a
    message instead of taking the whole dashboard down."""
    env = os.environ if env is None else env
    raw = {}
    cfg_path = Path(root) / "brain_share_config.json"
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            return BoardSettings(error=f"설정 파일을 읽을 수 없습니다: {e}")
    b = raw.get("board") or {}
    key = str(b.get("key") or env.get("BRAIN_BOARD_KEY") or "")
    owner = str(b.get("owner") or "대표").strip() or "대표"
    vault = str(b.get("export_vault_dir") or "")
    if not key:
        return BoardSettings(owner=owner, error=(
            "업무 보드 키가 설정되지 않았습니다. brain_share_config.json에 "
            '"board": {"key": "..."} 를 추가하거나 BRAIN_BOARD_KEY 환경변수를 '
            "설정한 뒤 대시보드를 다시 시작하세요."))
    if key == raw.get("read_key"):
        return BoardSettings(owner=owner, error=(
            "보드 키가 게이트웨이 read_key와 같습니다. 모든 leaf가 read_key를 "
            "갖고 있으므로 보드 키는 반드시 달라야 합니다."))
    if key == (raw.get("desk") or {}).get("key"):
        return BoardSettings(owner=owner, error=(
            "보드 키가 desk 키와 같습니다. 서로 다른 키를 쓰세요."))
    return BoardSettings(key=key, owner=owner, vault_dir=vault)


def _need(body: dict, field: str) -> str:
    v = body.get(field)
    return "" if v is None else str(v)


def handle(board: TaskBoard, settings: BoardSettings, method: str, path: str,
           headers, body: bytes):
    """Return (http_status, json_payload)."""
    if settings.error or not settings.key:
        return 503, {"error": settings.error or "업무 보드가 꺼져 있습니다"}
    given = (headers.get("X-Brain-Board-Key") or "").encode("utf-8")
    if not hmac.compare_digest(given, settings.key.encode("utf-8")):
        return 401, {"error": "보드 키가 올바르지 않습니다"}

    data = {}
    if method == "POST":
        if len(body) > MAX_BODY:
            return 413, {"error": "요청이 너무 큽니다"}
        ctype = (headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype != "application/json":
            return 415, {"error": "Content-Type은 application/json 이어야 합니다"}
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return 400, {"error": "JSON 형식이 올바르지 않습니다"}
        if not isinstance(data, dict):
            return 400, {"error": "JSON 객체를 보내야 합니다"}

    owner = settings.owner
    try:
        if path == "/api/tasks":
            if method == "GET":
                return 200, {"tasks": board.list(), "summary": board.summary(),
                             "owner": owner}
            if method == "POST":
                return 201, board.create(
                    _need(data, "title"), requester=owner,
                    description=_need(data, "description"),
                    assignee=_need(data, "assignee"),
                    priority=_need(data, "priority") or "normal",
                    due=_need(data, "due"),
                    division=_need(data, "division"),
                    sensitivity=_need(data, "sensitivity") or "internal")
            return 405, {"error": "허용되지 않는 메서드입니다"}

        m = _TASK_PATH.match(path)
        if not m:
            return 404, {"error": "없는 경로입니다"}
        tid, action = int(m.group(1)), m.group(2)
        if action is None:
            if method != "GET":
                return 405, {"error": "허용되지 않는 메서드입니다"}
            return 200, board.get(tid)
        if method != "POST":
            return 405, {"error": "허용되지 않는 메서드입니다"}

        if action == "assign":
            return 200, board.assign(tid, _need(data, "assignee"), actor=owner)
        if action == "comment":
            return 200, board.comment(tid, actor=owner, text=_need(data, "text"))
        if action == "reject":
            return 200, board.reject(tid, actor=owner,
                                     reason=_need(data, "reason"))
        if action == "block":
            return 200, board.block(tid, actor=owner,
                                    reason=_need(data, "reason"))
        if action == "unblock":
            return 200, board.unblock(tid, actor=owner,
                                      note=_need(data, "note"))
        if action == "approve":
            task = board.approve(tid, actor=owner, note=_need(data, "note"))
            if settings.vault_dir:
                # The approval stands even if the export fails; say so.
                try:
                    task["wiki_path"] = export_to_vault(task, settings.vault_dir)
                except Exception as e:
                    task["export_error"] = str(e)
            return 200, task
        return 404, {"error": f"알 수 없는 작업입니다: {action}"}
    except TaskNotFound as e:
        return 404, {"error": str(e)}
    except TaskError as e:
        return 409, {"error": str(e)}
