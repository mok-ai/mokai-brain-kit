import json
from io import BytesIO
from pathlib import Path
import pytest


def _get(handler_cls, path: str):
    """Call the handler in-process without opening a socket."""
    class _FakeReq:
        def __init__(self, path):
            self._path = path
            self.body = b""
            self._wfile = BytesIO()
        def makefile(self, mode, *a, **kw):
            if "r" in mode:
                return BytesIO(f"GET {self._path} HTTP/1.1\r\nHost: t\r\n\r\n".encode())
            return self._wfile
        def sendall(self, data):
            self._wfile.write(data)
    class _FakeSrv:
        def __init__(self): self.server_address = ("127.0.0.1", 0)
    req = _FakeReq(path)
    handler = handler_cls(req, ("127.0.0.1", 0), _FakeSrv())
    return req._wfile.getvalue()


def _parse_http(raw: bytes):
    head, _, body = raw.partition(b"\r\n\r\n")
    status = head.split(b"\r\n")[0].decode()
    return status, body


def test_api_status_returns_json_with_expected_keys(tmp_path):
    from brain_dashboard import make_handler
    (tmp_path / "incoming").mkdir()
    h = make_handler(tmp_path, ports=[59991])
    raw = _get(h, "/api/status")
    status, body = _parse_http(raw)
    assert "200 OK" in status
    data = json.loads(body.decode("utf-8"))
    assert set(data.keys()) >= {"generated_at", "root", "incoming",
                                 "backups", "synth", "graph", "servers"}


def test_root_serves_html_dashboard(tmp_path):
    from brain_dashboard import make_handler
    h = make_handler(tmp_path, ports=[])
    raw = _get(h, "/")
    status, body = _parse_http(raw)
    assert "200 OK" in status
    text = body.decode("utf-8", errors="replace")
    assert "<html" in text.lower()
    assert "/api/status" in text  # dashboard fetches this endpoint
    assert "brain kit" in text.lower() or "브레인" in text


def test_unknown_route_returns_404(tmp_path):
    from brain_dashboard import make_handler
    h = make_handler(tmp_path, ports=[])
    raw = _get(h, "/ghost/path")
    status, _ = _parse_http(raw)
    assert "404" in status


def test_make_handler_uses_provided_root_in_api_response(tmp_path):
    from brain_dashboard import make_handler
    h = make_handler(tmp_path, ports=[])
    raw = _get(h, "/api/status")
    _, body = _parse_http(raw)
    data = json.loads(body.decode("utf-8"))
    assert data["root"] == str(tmp_path)


def test_html_page_declares_utf8_charset(tmp_path):
    """Korean labels in the dashboard require utf-8 declaration."""
    from brain_dashboard import make_handler
    h = make_handler(tmp_path, ports=[])
    raw = _get(h, "/")
    _, body = _parse_http(raw)
    text = body.decode("utf-8", errors="replace")
    assert "utf-8" in text.lower()
