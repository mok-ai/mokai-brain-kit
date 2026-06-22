# brain_share/gateway_mcp.py
# 실행: python -m brain_share.gateway_mcp --config brain_share_config.json
import argparse, logging
from mcp.server.fastmcp import FastMCP
from brain_share.config import load_config
from brain_share.gateway_core import check_key, resolve_query, resolve_related
from brain_share.graph_gateway import graph_neighbors

log = logging.getLogger("brain_share")


def build_server(config, wiki_search, rag_search, related_fn, graph_store=None):
    logging.basicConfig(filename="brain_share_access.log", level=logging.INFO,
                        format="%(asctime)s %(message)s", encoding="utf-8")
    mcp = FastMCP("company-brain", host="0.0.0.0", port=config.share_port)

    def _auth(ctx):
        key = ""
        try:
            key = ctx.request_context.request.headers.get("X-Brain-Key", "")
        except Exception:
            key = ""
        return check_key(key, config)

    @mcp.tool()
    def search_company_brain(query: str, top_k: int = 5, ctx=None) -> list:
        if not _auth(ctx):
            return []
        rows = resolve_query(query, top_k, wiki_search, rag_search, config)
        log.info(f"search q='{query[:60]}' -> {len(rows)}")
        return rows

    @mcp.tool()
    def get_company_context(query: str, ctx=None) -> str:
        if not _auth(ctx):
            return ""
        rows = resolve_query(query, 5, wiki_search, rag_search, config)
        log.info(f"context q='{query[:60]}' -> {len(rows)}")
        return "\n\n".join(f"[{r['collection']}] {r['content']}" for r in rows)

    @mcp.tool()
    def related_in_brain(entity: str, top_k: int = 10, ctx=None) -> list:
        if not _auth(ctx):
            return []
        rows = resolve_related(entity, top_k, related_fn, config)
        log.info(f"related e='{entity}' -> {len(rows)}")
        return rows

    @mcp.tool()
    def graph_neighbors_tool(keyword: str, top_k: int = 10, ctx=None) -> list:
        if not _auth(ctx):
            return []
        if graph_store is None:
            return []
        rows = graph_neighbors(keyword, top_k, graph_store, config)
        log.info(f"graph keyword='{keyword}' -> {len(rows)}")
        return rows

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
    build_server(cfg, wiki_search, rag_search, related_fn, graph_store=store).run(transport="streamable-http")
