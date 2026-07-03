#!/usr/bin/env python3
"""
memory_mcp.py — 스머프 장기기억 MCP 서버 (로컬 Claude용 "출입구")

기존 저장소를 그대로 사용한다 — 새 저장소를 만들지 않는다.
로컬 RAG 서버(127.0.0.1:9210, chroma_db)에 HTTP로 읽고/쓴다.
소유자 전용이므로 민감정보 필터는 걸지 않는다(전체 접근).

도구:
  recall_memory(query, top_k=5)                  → 과거 기억 회상 (검색)
  save_memory(content, tags="", division="GENERAL", role="assistant")
                                                 → 새 기억을 RAG에 저장

등록(로컬 Claude, c:\\smurfs 에서):
  claude mcp add smurfs-memory -- py C:/smurfs/memory_mcp.py

의존성:  py -m pip install mcp
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

# ── 설정 (환경변수로 덮어쓰기 가능) ────────────────────────────
RAG_BASE = os.environ.get("RAG_BASE", "http://127.0.0.1:9210")
SEARCH_PATH = os.environ.get("RAG_SEARCH_PATH", "/memory/search")   # 확인됨 ✔
# 저장 엔드포인트 — memory_api.py 의 통합 저장 라우트(실측 확정 ✔).
#   POST /memory/store  body: {"type": conversation|decision|task|knowledge, "content": ..., ...}
#   서버가 type 별로 store_conversation/store_decision/store_task/store_knowledge 로 분기하며
#   기존 chroma_db·컬렉션(kim_*)을 그대로 사용한다. 새 저장소를 만들지 않는다.
SAVE_PATH = os.environ.get("RAG_SAVE_PATH", "/memory/store")
# 기본 저장 유형 — knowledge(지식/요약, 365일 보존)로 장기기억화. decision(영구)도 가능.
DEFAULT_MEM_TYPE = os.environ.get("RAG_MEM_TYPE", "knowledge")

mcp = FastMCP("smurfs-memory")


def _post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    url = RAG_BASE.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


@mcp.tool()
def recall_memory(query: str, top_k: int = 5) -> list:
    """과거 장기기억을 검색해 관련 기억을 돌려준다.

    Args:
        query: 찾고 싶은 내용(자연어).
        top_k: 최대 개수(기본 5).
    Returns:
        관련 기억 리스트. 각 항목은 content/collection/score/id/division/timestamp.
    """
    try:
        resp = _post(SEARCH_PATH, {"query": query, "top_k": top_k, "min_score": 0})
    except Exception as e:
        return [{"error": f"검색 실패: {type(e).__name__}: {e}", "url": RAG_BASE + SEARCH_PATH}]
    rows = resp.get("results", resp.get("matches", []))
    out = []
    for r in rows:
        m = r.get("metadata", {}) or {}
        out.append({
            "content": r.get("content", ""),
            "collection": r.get("collection", ""),
            "score": r.get("score"),
            "id": r.get("id", ""),
            "division": m.get("division", ""),
            "tags": m.get("tags", ""),
            "timestamp": m.get("timestamp", ""),
        })
    return out


@mcp.tool()
def save_memory(content: str, mem_type: str = DEFAULT_MEM_TYPE, title: str = "",
                tags: str = "", division: str = "", importance: str = "high",
                role: str = "assistant") -> dict:
    """새 기억을 장기기억(RAG)에 저장한다. 기존 저장소·컬렉션(kim_*)을 그대로 사용.

    memory_api 의 통합 저장 라우트(POST /memory/store)를 호출하며, mem_type 에 따라
    서버가 알맞은 컬렉션(decisions/knowledge/tasks/conversations)에 임베딩·저장한다.

    Args:
        content: 저장할 내용(필수).
        mem_type: 저장 유형 — "knowledge"(지식/요약, 365일·기본) | "decision"(의사결정, 영구)
                  | "task"(업무, 90일) | "conversation"(대화, 30일).
        title: 제목/주제. knowledge의 topic, decision의 title, task의 task_name 으로 쓰임
               (미지정 시 content 앞부분에서 자동 생성).
        tags: 쉼표구분 태그(decision·conversation 에만 반영됨).
        division: 사업부 분류(빈값이면 서버가 일부 유형에서 자동 감지).
        importance: decision 중요도 — "critical" | "high"(기본) | "normal".
        role: conversation 유형의 발화자(user/assistant, 기본 assistant).
    Returns:
        저장 결과(success, stored 청크 수, ids, type 등).
    """
    if not content.strip():
        return {"success": False, "error": "빈 content 는 저장하지 않음"}

    mem_type = (mem_type or DEFAULT_MEM_TYPE).strip().lower()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # /memory/store 는 type 별로 필드가 다르다 (memory_api.store 분기와 1:1 대응).
    if mem_type == "decision":
        payload = {
            "type": "decision",
            "title": title or content.strip()[:50],
            "content": content,
            "division": division,
            "importance": importance,
            "tags": tag_list,
        }
    elif mem_type == "task":
        payload = {
            "type": "task",
            "task_name": title or content.strip()[:50],
            "content": content,
            "division": division,
        }
    elif mem_type == "conversation":
        payload = {
            "type": "conversation",
            "role": role,
            "content": content,
            "division": division,
            "tags": tag_list,
        }
    else:  # knowledge (기본)
        mem_type = "knowledge"
        payload = {
            "type": "knowledge",
            "topic": title or content.strip()[:50],
            "content": content,
            "source": "smurfs-memory-mcp",
            "division": division,
        }

    try:
        resp = _post(SAVE_PATH, payload)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return {"success": False,
                "error": f"저장 실패 HTTP {e.code} at {SAVE_PATH}", "body": body}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}",
                "url": RAG_BASE + SAVE_PATH}

    ts = datetime.now(timezone.utc).astimezone().isoformat()
    ok = bool(resp.get("success", True)) if isinstance(resp, dict) else True
    return {"success": ok, "type": mem_type, "response": resp, "timestamp": ts}


if __name__ == "__main__":
    print("smurfs-memory MCP up (stdio). RAG_BASE=" + RAG_BASE, file=sys.stderr)
    mcp.run()
