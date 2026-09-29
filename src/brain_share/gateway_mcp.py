# brain_share/gateway_mcp.py
# 실행: python -m brain_share.gateway_mcp --config brain_share_config.json
import argparse, logging, os
from mcp.server.fastmcp import FastMCP, Context
from brain_share.config import load_config
from brain_share.gateway_core import check_key, resolve_query, resolve_related
from brain_share.graph_gateway import graph_neighbors
from brain_share.task_board import TaskError, is_private

log = logging.getLogger("brain_share")


def build_server(config, wiki_search, rag_search, related_fn, graph_store=None,
                 task_board=None, owner_name="대표"):
    logging.basicConfig(filename="brain_share_access.log", level=logging.INFO,
                        format="%(asctime)s %(message)s", encoding="utf-8")
    # Default loopback only; set BRAIN_SHARE_HOST=0.0.0.0 to expose on LAN.
    bind_host = os.environ.get("BRAIN_SHARE_HOST", "127.0.0.1")
    mcp = FastMCP("company-brain", host=bind_host, port=config.share_port)

    def _auth(ctx):
        key = ""
        try:
            key = ctx.request_context.request.headers.get("X-Brain-Key", "")
        except Exception:
            key = ""
        return check_key(key, config)

    @mcp.tool()
    def search_company_brain(query: str, top_k: int = 5, ctx: Context = None) -> list:
        if not _auth(ctx):
            return []
        rows = resolve_query(query, top_k, wiki_search, rag_search, config)
        log.info(f"search q='{query[:60]}' -> {len(rows)}")
        return rows

    @mcp.tool()
    def get_company_context(query: str, ctx: Context = None) -> str:
        if not _auth(ctx):
            return ""
        rows = resolve_query(query, 5, wiki_search, rag_search, config)
        log.info(f"context q='{query[:60]}' -> {len(rows)}")
        return "\n\n".join(f"[{r['collection']}] {r['content']}" for r in rows)

    @mcp.tool()
    def related_in_brain(entity: str, top_k: int = 10, ctx: Context = None) -> list:
        if not _auth(ctx):
            return []
        rows = resolve_related(entity, top_k, related_fn, config)
        log.info(f"related e='{entity}' -> {len(rows)}")
        return rows

    @mcp.tool()
    def graph_neighbors_tool(keyword: str, top_k: int = 10, ctx: Context = None) -> list:
        if not _auth(ctx):
            return []
        if graph_store is None:
            return []
        rows = graph_neighbors(keyword, top_k, graph_store, config)
        log.info(f"graph keyword='{keyword}' -> {len(rows)}")
        return rows

    # ── Task board (agent side) ─────────────────────────────────────
    # Agents may list, create, claim, report, comment and block. Approval
    # and rejection stay on the owner's board page: an agent cannot sign off
    # its own work. Private tasks (confidential or a blocked division) are
    # invisible here — acting on one reads as "not found".
    # `agent` is self-declared (every leaf shares read_key), so it may not
    # impersonate the owner.

    def _task_call(ctx, fn, *, agent=None):
        if not _auth(ctx):
            return {"error": "unauthorized"}
        if task_board is None:
            return {"error": "task board not configured on this hub"}
        if agent is not None:
            name = str(agent or "").strip()
            if not name:
                return {"error": "agent 이름이 필요합니다"}
            if name == owner_name:
                return {"error": "agent 이름으로 보드 소유자 이름을 쓸 수 없습니다"}
        try:
            return fn()
        except TaskError as e:
            return {"error": str(e)}

    def _visible(task_id):
        task = task_board.get(task_id)
        if is_private(task, config):
            raise TaskError(f"업무 #{task_id}을(를) 찾을 수 없습니다")
        return task

    @mcp.tool()
    def task_list(status: str = "", assignee: str = "", ctx: Context = None) -> list:
        """List board tasks (optionally by status: pending, in_progress,
        blocked, review, done; or by assignee)."""
        res = _task_call(ctx, lambda: [
            t for t in task_board.list(status=status or None,
                                       assignee=assignee or None)
            if not is_private(t, config)])
        return res if isinstance(res, list) else []

    @mcp.tool()
    def task_get(task_id: int, ctx: Context = None) -> dict:
        """One task with its full history (comments, reports, rejections)."""
        return _task_call(ctx, lambda: _visible(task_id))

    @mcp.tool()
    def task_create(title: str, agent: str, description: str = "",
                    priority: str = "normal", due: str = "",
                    assignee: str = "", ctx: Context = None) -> dict:
        """Open a task (e.g. a question or decision for the owner)."""
        def go():
            t = task_board.create(title, requester=agent.strip(),
                                  description=description, priority=priority,
                                  due=due, assignee=assignee,
                                  sensitivity="internal")
            log.info(f"task create #{t['id']} by {agent}")
            return t
        return _task_call(ctx, go, agent=agent)

    @mcp.tool()
    def task_claim(task_id: int, agent: str, ctx: Context = None) -> dict:
        """Start a pending task. Fails if it is assigned to someone else."""
        def go():
            _visible(task_id)
            t = task_board.claim(task_id, agent=agent.strip())
            log.info(f"task claim #{task_id} by {agent}")
            return t
        return _task_call(ctx, go, agent=agent)

    @mcp.tool()
    def task_report(task_id: int, agent: str, summary: str,
                    outputs: list[str] = None, lessons: str = "",
                    ctx: Context = None) -> dict:
        """Report finished work; the task waits for the owner's approval."""
        def go():
            _visible(task_id)
            t = task_board.report(task_id, agent=agent.strip(),
                                  summary=summary, outputs=outputs or [],
                                  lessons=lessons)
            log.info(f"task report #{task_id} by {agent}")
            return t
        return _task_call(ctx, go, agent=agent)

    @mcp.tool()
    def task_comment(task_id: int, agent: str, text: str,
                     ctx: Context = None) -> dict:
        """Add a comment to a task's history."""
        def go():
            _visible(task_id)
            return task_board.comment(task_id, actor=agent.strip(), text=text)
        return _task_call(ctx, go, agent=agent)

    @mcp.tool()
    def task_block(task_id: int, agent: str, reason: str,
                   ctx: Context = None) -> dict:
        """Mark your in-progress task as blocked, with the reason."""
        def go():
            t = _visible(task_id)
            if t["assignee"] != agent.strip():
                raise TaskError("담당자만 막힘으로 표시할 수 있습니다")
            return task_board.block(task_id, actor=agent.strip(), reason=reason)
        return _task_call(ctx, go, agent=agent)

    return mcp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="brain_share_config.json")
    args = ap.parse_args()
    cfg = load_config(args.config)
    from brain_share.mm_adapter import make_backends  # Task 10
    wiki_search, rag_search, related_fn = make_backends(cfg)
    from pathlib import Path
    from brain_share.graph_store import SqliteGraphStore
    config_path = Path(args.config)
    graph_db_path = config_path.parent / "graph.db"
    store = SqliteGraphStore(str(graph_db_path))
    from brain_share.board_api import board_settings
    from brain_share.task_board import TaskBoard
    board = TaskBoard(config_path.parent / "task_board.db")
    owner = board_settings(config_path.parent).owner
    build_server(cfg, wiki_search, rag_search, related_fn, graph_store=store,
                 task_board=board, owner_name=owner).run(transport="streamable-http")
