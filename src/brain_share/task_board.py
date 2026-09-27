"""Task board — the owner <-> agent collaboration flow (SQLite, stdlib only).

A task moves through a small, enforced state machine:

    pending --claim--> in_progress --report--> review --approve--> done
                         |    ^                  |
                   block |    | unblock          | reject (reason required)
                         v    |                  v
                        blocked               in_progress

Who may do what is decided by the caller, not here: the local board page
(owner, board key) creates / assigns / approves / rejects; agents reach the
board through the MCP gateway, which exposes claim / report / comment / block
but never approve — an agent cannot sign off its own work.

Every change is appended to an `events` table, so the detail view is a full
history and nothing is overwritten silently. Approved tasks can be exported
to the wiki vault as a TaskRecord page, the same shape task_record.py has
always produced.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

from brain_share.task_record import TaskRecord, to_wiki_page
from brain_share.wiki_page import render_page

STATUSES = ("pending", "in_progress", "blocked", "review", "done")
PRIORITIES = ("low", "normal", "high", "urgent")
STATUS_LABELS = {"pending": "대기", "in_progress": "진행", "blocked": "막힘",
                 "review": "승인 대기", "done": "완료"}
KIND_LABELS = {"claimed": "착수", "blocked": "막힘 처리", "unblocked": "막힘 해제",
               "reported": "보고", "approved": "승인", "rejected": "반려"}
_FIELD_LABELS = {"title": "제목", "requester": "요청자", "assignee": "담당자",
                 "actor": "작성자", "agent": "에이전트", "division": "부서",
                 "sensitivity": "민감도", "description": "설명",
                 "reason": "사유", "note": "메모", "summary": "보고 내용",
                 "lessons": "교훈", "comment": "코멘트", "output": "산출물"}
# Tasks at these sensitivity levels never leave the hub through the gateway.
PRIVATE_SENSITIVITY = ("confidential", "secret", "restricted")

MAX_TITLE = 200
MAX_TEXT = 5000
MAX_NAME = 64
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    requester TEXT NOT NULL,
    assignee TEXT NOT NULL DEFAULT '',
    due TEXT NOT NULL DEFAULT '',
    division TEXT NOT NULL DEFAULT '',
    sensitivity TEXT NOT NULL DEFAULT 'internal',
    outputs TEXT NOT NULL DEFAULT '[]',
    lessons TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_task ON events(task_id, id);
"""

_TASK_COLS = ("id", "title", "description", "status", "priority", "requester",
              "assignee", "due", "division", "sensitivity", "outputs",
              "lessons", "created_at", "updated_at")


class TaskError(ValueError):
    """A request the board refuses (bad input or illegal transition)."""


class TaskNotFound(TaskError):
    pass


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _name(value, field: str, *, required: bool = True) -> str:
    v = str(value or "").strip()
    if required and not v:
        raise TaskError(f"{_FIELD_LABELS.get(field, field)}을(를) 입력하세요")
    if len(v) > MAX_NAME:
        raise TaskError(
            f"{_FIELD_LABELS.get(field, field)}이(가) 너무 깁니다 (최대 {MAX_NAME}자)")
    return v


def _text(value, field: str, *, required: bool = False,
          limit: int = MAX_TEXT) -> str:
    v = str(value or "").strip()
    if required and not v:
        raise TaskError(f"{_FIELD_LABELS.get(field, field)}을(를) 입력하세요")
    if len(v) > limit:
        raise TaskError(
            f"{_FIELD_LABELS.get(field, field)}이(가) 너무 깁니다 (최대 {limit}자)")
    return v


def _due(value) -> str:
    v = str(value or "").strip()
    if not v:
        return ""
    if not _DATE_RE.match(v):
        raise TaskError("기한은 YYYY-MM-DD 형식이어야 합니다")
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        raise TaskError("기한이 올바른 날짜가 아닙니다")
    return v


def _priority(value) -> str:
    v = str(value or "normal").strip() or "normal"
    if v not in PRIORITIES:
        raise TaskError(f"우선순위는 {', '.join(PRIORITIES)} 중 하나여야 합니다")
    return v


def _outputs(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise TaskError("산출물은 문자열 목록이어야 합니다")
    out = [_text(v, "output", limit=500) for v in value]
    return [v for v in out if v][:50]


class TaskBoard:
    def __init__(self, db_path, *, clock=time.time):
        self.db_path = str(db_path)
        self._clock = clock
        # One connection shared by the dashboard's request threads: every
        # read and write goes through this lock (re-entrant, since writes
        # read the row they change).
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextlib.contextmanager
    def _atomic(self):
        """Serialize writers in-process and make multi-statement writes
        all-or-nothing (a status change and its history row go together)."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    # ─────────────────────────── reads ───────────────────────────

    def _row(self, task_id) -> sqlite3.Row:
        try:
            tid = int(task_id)
        except (TypeError, ValueError):
            raise TaskNotFound(f"업무 {task_id!r}을(를) 찾을 수 없습니다")
        row = self._conn.execute(
            f"SELECT {', '.join(_TASK_COLS)} FROM tasks WHERE id=?",
            (tid,)).fetchone()
        if row is None:
            raise TaskNotFound(f"업무 #{tid}을(를) 찾을 수 없습니다")
        return row

    @staticmethod
    def _to_dict(row) -> dict:
        d = {k: row[k] for k in _TASK_COLS}
        try:
            d["outputs"] = json.loads(d["outputs"] or "[]")
        except ValueError:
            d["outputs"] = []
        return d

    def get(self, task_id) -> dict:
        with self._lock:
            task = self._to_dict(self._row(task_id))
            task["events"] = [dict(r) for r in self._conn.execute(
                "SELECT at, actor, kind, text FROM events WHERE task_id=? "
                "ORDER BY id", (task["id"],)).fetchall()]
        return task

    def list(self, *, status: str = None, assignee: str = None) -> list:
        sql = f"SELECT {', '.join(_TASK_COLS)} FROM tasks"
        where, args = [], []
        if status:
            if status not in STATUSES:
                raise TaskError(f"상태는 {', '.join(STATUSES)} 중 하나여야 합니다")
            where.append("status=?")
            args.append(status)
        if assignee:
            where.append("assignee=?")
            args.append(assignee)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += (" ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1"
                " WHEN 'normal' THEN 2 ELSE 3 END, (due = ''), due, id")
        with self._lock:
            return [self._to_dict(r) for r in self._conn.execute(sql, args)]

    def summary(self, *, today: str = None) -> dict:
        today = today or datetime.date.fromtimestamp(self._clock()).isoformat()
        with self._lock:
            return _summary(self._conn, today)

    # ─────────────────────────── writes ──────────────────────────

    def _event(self, task_id: int, actor: str, kind: str, text: str = "",
               **fields) -> None:
        now = _iso(self._clock())
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self._conn.execute(
                f"UPDATE tasks SET {sets}, updated_at=? WHERE id=?",
                (*fields.values(), now, task_id))
        else:
            self._conn.execute("UPDATE tasks SET updated_at=? WHERE id=?",
                               (now, task_id))
        self._conn.execute(
            "INSERT INTO events(task_id, at, actor, kind, text) "
            "VALUES (?, ?, ?, ?, ?)", (task_id, now, actor, kind, text))

    def _transition(self, task_id, actor, kind, *, frm, to, text="",
                    _only_assignee=None, **fields) -> dict:
        """_only_assignee: None = anyone; False = unassigned or already the
        actor's (claim); True = must be the actor's (report). Checked inside
        the transaction so two agents can't both win a claim."""
        with self._atomic():
            row = self._row(task_id)
            if row["status"] not in frm:
                raise TaskError(
                    f"'{STATUS_LABELS[row['status']]}' 상태에서는 "
                    f"{KIND_LABELS[kind]}할 수 없습니다")
            if _only_assignee is False and row["assignee"] \
                    and row["assignee"] != actor:
                raise TaskError(f"이미 {row['assignee']}에게 배정된 업무입니다")
            if _only_assignee is True and row["assignee"] != actor:
                raise TaskError("담당자만 보고할 수 있습니다")
            self._event(row["id"], actor, kind, text, status=to, **fields)
        return self.get(row["id"])

    def create(self, title, *, requester, description="", assignee="",
               priority="normal", due="", division="",
               sensitivity="internal") -> dict:
        title = _text(title, "title", required=True, limit=MAX_TITLE)
        requester = _name(requester, "requester")
        assignee = _name(assignee, "assignee", required=False)
        description = _text(description, "description")
        priority = _priority(priority)
        due = _due(due)
        division = _name(division, "division", required=False)
        sensitivity = _name(sensitivity or "internal", "sensitivity")
        now = _iso(self._clock())
        with self._atomic():
            cur = self._conn.execute(
                "INSERT INTO tasks(title, description, status, priority,"
                " requester, assignee, due, division, sensitivity,"
                " created_at, updated_at)"
                " VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (title, description, priority, requester, assignee, due,
                     division, sensitivity, now, now))
            tid = cur.lastrowid
            self._conn.execute(
                "INSERT INTO events(task_id, at, actor, kind, text) "
                "VALUES (?, ?, ?, 'created', ?)",
                (tid, now, requester,
                 f"담당: {assignee}" if assignee else ""))
        return self.get(tid)

    def assign(self, task_id, assignee, *, actor) -> dict:
        assignee = _name(assignee, "assignee")
        actor = _name(actor, "actor")
        with self._atomic():
            row = self._row(task_id)
            if row["status"] == "done":
                raise TaskError("완료된 업무는 담당자를 바꿀 수 없습니다")
            self._event(row["id"], actor, "assigned", assignee,
                        assignee=assignee)
        return self.get(row["id"])

    def claim(self, task_id, *, agent) -> dict:
        agent = _name(agent, "agent")
        return self._transition(task_id, agent, "claimed", frm=("pending",),
                                to="in_progress", assignee=agent,
                                _only_assignee=False)

    def block(self, task_id, *, actor, reason) -> dict:
        return self._transition(
            task_id, _name(actor, "actor"), "blocked",
            frm=("in_progress",), to="blocked",
            text=_text(reason, "reason", required=True))

    def unblock(self, task_id, *, actor, note="") -> dict:
        return self._transition(
            task_id, _name(actor, "actor"), "unblocked",
            frm=("blocked",), to="in_progress", text=_text(note, "note"))

    def report(self, task_id, *, agent, summary, outputs=None,
               lessons="") -> dict:
        agent = _name(agent, "agent")
        return self._transition(
            task_id, agent, "reported", frm=("in_progress",), to="review",
            _only_assignee=True,
            text=_text(summary, "summary", required=True),
            outputs=json.dumps(_outputs(outputs), ensure_ascii=False),
            lessons=_text(lessons, "lessons"))

    def approve(self, task_id, *, actor, note="") -> dict:
        return self._transition(
            task_id, _name(actor, "actor"), "approved",
            frm=("review",), to="done", text=_text(note, "note"))

    def reject(self, task_id, *, actor, reason) -> dict:
        return self._transition(
            task_id, _name(actor, "actor"), "rejected",
            frm=("review",), to="in_progress",
            text=_text(reason, "reason", required=True))

    def comment(self, task_id, *, actor, text) -> dict:
        actor = _name(actor, "actor")
        text = _text(text, "comment", required=True)
        with self._atomic():
            row = self._row(task_id)
            self._event(row["id"], actor, "commented", text)
        return self.get(row["id"])


# ─────────────────────────── helpers ─────────────────────────────

def is_private(task: dict, config) -> bool:
    """True when a task must not be shown outside the owner's board."""
    if task.get("sensitivity") in PRIVATE_SENSITIVITY:
        return True
    return bool(task.get("division")) and \
        task["division"] in (config.blocked_divisions or [])


def to_task_record(task: dict) -> TaskRecord:
    reports = [e["text"] for e in task.get("events", [])
               if e["kind"] == "reported"]
    lessons = task.get("lessons") or ""
    if reports:
        lessons = (lessons + "\n\n" if lessons else "") + \
            "최종 보고: " + reports[-1]
    return TaskRecord(
        task=task["title"], status="done" if task["status"] == "done"
        else ("in_progress" if task["status"] == "review" else task["status"]),
        outputs=list(task.get("outputs") or []), links=[],
        lessons=lessons, division=task.get("division") or "",
        sensitivity=task.get("sensitivity") or "internal",
        updated=(task.get("updated_at") or "")[:10])


def export_to_vault(task: dict, vault_dir) -> str:
    """Write an approved task as a wiki page. Returns the file path."""
    if task.get("status") != "done":
        raise TaskError("승인 완료된 업무만 위키로 내보낼 수 있습니다")
    page = to_wiki_page(to_task_record(task))
    page.topic = f"task_{int(task['id']):05d}"
    ns_dir = Path(vault_dir) / (page.namespace or "GENERAL")
    os.makedirs(ns_dir, exist_ok=True)
    path = ns_dir / f"{page.topic}.md"
    path.write_text(render_page(page), encoding="utf-8")
    return str(path)


def read_summary(db_path) -> dict | None:
    """Summary without creating the database (for read-only reporters)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return _summary(conn, datetime.date.today().isoformat())
        finally:
            conn.close()
    except Exception:
        return None


def _summary(conn, today: str) -> dict:
    counts = {s: 0 for s in STATUSES}
    for s, n in conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"):
        if s in counts:
            counts[s] = n
    overdue = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE due != '' AND due < ? "
        "AND status != 'done'", (today,)).fetchone()[0]
    return {"counts": counts, "total": sum(counts.values()),
            "awaiting_approval": counts["review"],
            "blocked": counts["blocked"], "overdue": overdue}
