#!/usr/bin/env python3
"""brain_dashboard.py — Local hub-operator dashboard for Mokai Brain Kit.

Serves the status page (`/`, read-only, from
brain_share.dashboard_scanner.collect_all() via `/api/status`) and the task
board (`/board`, `/api/tasks*`, owner actions — needs the board key, see
brain_share.board_api). Binds to 127.0.0.1 by default. LAN opt-in via
BRAIN_DASHBOARD_HOST=0.0.0.0.

CLI:
  python brain_dashboard.py --root C:/brainkit/memory
  python brain_dashboard.py --root C:/brainkit/memory --port 9213
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make the module importable both as top-level script and via -m
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from brain_share.board_api import MAX_BODY, BoardSettings, board_settings, handle  # noqa: E402
from brain_share.board_page import BOARD_HTML  # noqa: E402
from brain_share.dashboard_scanner import collect_all  # noqa: E402
from brain_share.task_board import TaskBoard  # noqa: E402


_DASHBOARD_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mokai Brain Kit — Dashboard</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%A7%A0%3C/text%3E%3C/svg%3E">
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
         margin: 0; padding: 24px; background: #0f172a; color: #e2e8f0; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .sub { color: #94a3b8; font-size: 13px; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 15px; color: #38bdf8; letter-spacing: .3px; }
  .kv { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px dashed #334155; }
  .kv:last-child { border: none; }
  .kv .k { color: #94a3b8; }
  .kv .v { color: #f1f5f9; font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 13px; }
  .kv .v.badge-ok { color: #4ade80; }
  .kv .v.badge-down { color: #f87171; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #334155; }
  th { color: #94a3b8; font-weight: 500; }
  .foot { color: #64748b; font-size: 11px; margin-top: 16px; }
  header { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-bottom: 4px; }
  nav { display: flex; gap: 4px; }
  nav a { padding: 6px 12px; border-radius: 8px; text-decoration: none; color: #94a3b8; font-size: 14px; }
  nav a:hover { background: #1e293b; color: #e2e8f0; }
  nav a.on { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; }
  @media (max-width: 640px) { body { padding: 14px 16px; } .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
<h1>🧠 Mokai Brain Kit — Hub Dashboard</h1>
<nav aria-label="대시보드 메뉴">
  <a href="/" class="on" aria-current="page">상태</a>
  <a href="/board">업무 보드</a>
</nav>
</header>
<div class="sub" id="sub">loading…</div>
<div class="grid" id="grid"></div>
<div class="foot">auto-refresh every 30s · <span id="ver"></span></div>
<script>
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024*1024) return (n/1024).toFixed(1) + " KB";
  if (n < 1024*1024*1024) return (n/1024/1024).toFixed(1) + " MB";
  return (n/1024/1024/1024).toFixed(2) + " GB";
}
function esc(s) { return String(s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function refresh() {
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    render(d);
  } catch (e) {
    document.getElementById("sub").textContent = "fetch failed: " + e;
  }
}
function render(d) {
  document.getElementById("sub").textContent =
    "root: " + d.root + "  ·  updated: " + d.generated_at;
  const g = document.getElementById("grid");
  g.innerHTML = "";

  // Servers
  const svEntries = Object.entries(d.servers || {});
  let svHtml = "";
  for (const [p, live] of svEntries) {
    svHtml += `<div class="kv"><span class="k">:${p}</span>` +
              `<span class="v ${live?'badge-ok':'badge-down'}">` +
              (live ? "LISTEN" : "DOWN") + "</span></div>";
  }
  g.insertAdjacentHTML("beforeend", `<div class="card"><h2>Servers</h2>${svHtml || "(none)"}</div>`);

  // Incoming per-node
  const inc = d.incoming || {};
  let incHtml = `<div class="kv"><span class="k">total items</span><span class="v">${inc.total_items}</span></div>` +
                `<div class="kv"><span class="k">total size</span><span class="v">${fmtBytes(inc.total_size_bytes||0)}</span></div>`;
  const nodes = Object.entries(inc.nodes || {});
  if (nodes.length) {
    incHtml += `<table><tr><th>node</th><th>items</th><th>size</th><th>last upload</th></tr>`;
    for (const [n, s] of nodes) {
      incHtml += `<tr><td>${esc(n)}</td><td>${s.items}</td>` +
                 `<td>${fmtBytes(s.size_bytes)}</td>` +
                 `<td>${esc(s.last_ts || "-")}</td></tr>`;
    }
    incHtml += `</table>`;
  }
  g.insertAdjacentHTML("beforeend", `<div class="card"><h2>Incoming (per leaf)</h2>${incHtml}</div>`);

  // Backups
  const bk = d.backups || [];
  let bkHtml = "";
  if (bk.length) {
    bkHtml = `<table><tr><th>date</th><th>size</th><th>chroma sha</th></tr>`;
    for (const b of bk) {
      bkHtml += `<tr><td>${esc(b.date)}</td><td>${fmtBytes(b.size_bytes)}</td>` +
                `<td>${esc(b.sha_prefixes && b.sha_prefixes['chroma_db.zip'] || '-')}</td></tr>`;
    }
    bkHtml += `</table>`;
  } else {
    bkHtml = `<div class="kv"><span class="k">no snapshots</span><span class="v">–</span></div>`;
  }
  g.insertAdjacentHTML("beforeend", `<div class="card"><h2>Backups</h2>${bkHtml}</div>`);

  // Synth watermark
  const sy = d.synth || {};
  let syHtml = `<div class="kv"><span class="k">topics canonicalized</span><span class="v">${sy.count}</span></div>`;
  for (const t of (sy.topics || []).slice(0, 6)) {
    syHtml += `<div class="kv"><span class="k">${esc(t.topic)}</span><span class="v">${esc(t.latest_id||"-").slice(0,10)}</span></div>`;
  }
  g.insertAdjacentHTML("beforeend", `<div class="card"><h2>Synth watermark</h2>${syHtml}</div>`);

  // Graph
  const gr = d.graph || {};
  let grHtml = `<div class="kv"><span class="k">nodes</span><span class="v">${gr.nodes}</span></div>` +
               `<div class="kv"><span class="k">edges</span><span class="v">${gr.edges}</span></div>`;
  if ((gr.top_nodes||[]).length) {
    grHtml += `<table><tr><th>node</th><th>degree</th></tr>`;
    for (const n of gr.top_nodes.slice(0, 8)) {
      grHtml += `<tr><td>${esc(n.name)}</td><td>${n.degree}</td></tr>`;
    }
    grHtml += `</table>`;
  }
  g.insertAdjacentHTML("beforeend", `<div class="card"><h2>Relation graph</h2>${grHtml}</div>`);
}
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
"""


def make_handler(root, *, ports=None, dashboard_html: str = None,
                 board: TaskBoard = None, board_cfg: BoardSettings = None):
    """Return a BaseHTTPRequestHandler subclass with root/ports baked in.

    board/board_cfg default to <root>/task_board.db and the `board` section
    of <root>/brain_share_config.json."""
    _root = Path(root)
    _ports = ports if ports is not None else [9210, 9211, 9212]
    _html = (dashboard_html if dashboard_html is not None else _DASHBOARD_HTML)
    _board_cfg = board_cfg if board_cfg is not None else board_settings(_root)
    _board = board
    if _board is None and _board_cfg.key and not _board_cfg.error:
        _board = TaskBoard(_root / "task_board.db")

    class _Handler(BaseHTTPRequestHandler):
        # Suppress default access log noise in tests
        def log_message(self, format, *args):
            pass

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _board(self, method: str, body: bytes = b"") -> None:
            status, payload = handle(_board, _board_cfg, method, self.path,
                                     self.headers, body)
            self._send_json(status, payload)

        def do_GET(self):
            if self.path == "/api/status":
                self._send_json(200, collect_all(_root, ports=_ports))
            elif self.path == "/" or self.path == "/index.html":
                body = _html.encode("utf-8")
                self._send(200, body, "text/html; charset=utf-8")
            elif self.path == "/board":
                self._send(200, BOARD_HTML.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif self.path.startswith("/api/tasks"):
                self._board("GET")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self.path.startswith("/api/tasks"):
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                # Don't read an oversized body — answer and drop the connection.
                self.close_connection = True
                self._send_json(413, {"error": "요청이 너무 큽니다"})
                return
            self._board("POST", self.rfile.read(length))

    return _Handler


def run_server(root, *, host: str = None, port: int = None, ports=None) -> None:
    """Start blocking HTTP server on host:port."""
    bind_host = host or os.environ.get("BRAIN_DASHBOARD_HOST", "127.0.0.1")
    bind_port = int(port or os.environ.get("BRAIN_DASHBOARD_PORT", "9213"))
    handler = make_handler(Path(root), ports=ports)
    srv = ThreadingHTTPServer((bind_host, bind_port), handler)
    print(f"[dashboard] listening on {bind_host}:{bind_port}  root={root}")
    cfg = board_settings(Path(root))
    print("[dashboard] task board: " +
          ("on  (/board)" if cfg.key and not cfg.error else f"off — {cfg.error}"))
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="Mokai Brain Kit local dashboard")
    ap.add_argument("--root", default=r"C:\brainkit\memory")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    run_server(args.root, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
