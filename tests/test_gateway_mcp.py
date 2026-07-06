# v3.2.2 regression: MCP tool signatures must annotate ctx as Context.
# Without the annotation FastMCP leaves Tool.context_kwarg = None and never
# injects the request context, so _auth() cannot read X-Brain-Key and every
# live MCP client silently gets empty results. Unit tests that pass a fake
# ctx directly to the function never exercise that injection path — this
# file pins it down via FastMCP's own registration metadata.
import pytest

from brain_share.config import BrainShareConfig
from brain_share import gateway_mcp

TOOL_NAMES = ["search_company_brain", "get_company_context",
              "related_in_brain", "graph_neighbors_tool"]


def cfg():
    return BrainShareConfig(role="HUB", read_key="secret-key",
                            allowed_collections=["wiki", "knowledge"])


def row(id):
    return {"id": id, "content": "wiki body", "score": 0.9,
            "collection": "wiki", "metadata": {"division": "TECH"}}


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # keep brain_share_access.log out of the repo
    wiki = lambda q, k: [row("w1")]
    rag = lambda q, k: []
    related = lambda e, k: [row("r1")]
    server = gateway_mcp.build_server(cfg(), wiki, rag, related)
    return {t.name: t for t in server._tool_manager.list_tools()}


class FakeCtx:
    """Mimics the injected Context just enough for _auth()."""
    def __init__(self, key):
        class _Request:
            headers = {"X-Brain-Key": key}
        class _RequestContext:
            request = _Request()
        self.request_context = _RequestContext()


def test_every_tool_gets_context_injected(tools):
    assert set(TOOL_NAMES) <= set(tools)
    for name in TOOL_NAMES:
        assert tools[name].context_kwarg == "ctx", (
            f"{name}: ctx must be annotated as Context, otherwise FastMCP "
            "never injects the request context and X-Brain-Key auth always "
            "fails for real clients")


def test_tools_fail_closed_without_context(tools):
    assert tools["search_company_brain"].fn("q", 5, None) == []
    assert tools["get_company_context"].fn("q", None) == ""
    assert tools["related_in_brain"].fn("e", 5, None) == []
    assert tools["graph_neighbors_tool"].fn("k", 5, None) == []


def test_tools_serve_with_valid_key(tools):
    ctx = FakeCtx("secret-key")
    assert [r["id"] for r in tools["search_company_brain"].fn("q", 5, ctx)] == ["w1"]
    assert "wiki body" in tools["get_company_context"].fn("q", ctx)
    assert [r["id"] for r in tools["related_in_brain"].fn("e", 5, ctx)] == ["r1"]
    # graph_store=None → authenticated but no graph backend → empty
    assert tools["graph_neighbors_tool"].fn("k", 5, ctx) == []


def test_tools_reject_wrong_key(tools):
    ctx = FakeCtx("wrong-key")
    assert tools["search_company_brain"].fn("q", 5, ctx) == []
    assert tools["get_company_context"].fn("q", ctx) == ""
    assert tools["related_in_brain"].fn("e", 5, ctx) == []
