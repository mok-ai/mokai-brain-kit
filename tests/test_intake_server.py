import json
import pytest
from brain_share.config import BrainShareConfig
from brain_share.intake_server import process_batch


def cfg():
    return BrainShareConfig(role="HUB", read_key="k",
                            blocked_divisions=["ACCT"],
                            allowed_collections=["knowledge","incoming"],
                            blocked_keyword_patterns=["secret"])


def it(id, content="hello", division="TECH", collection="knowledge"):
    return {"id": id, "content": content, "collection": collection,
            "metadata": {"division": division}}


def test_process_batch_accepts_normal_items_and_calls_sink():
    sunk = []
    out = process_batch("n1", [it("a"), it("b")], cfg(), set(),
                       lambda node, item: sunk.append((node, item["id"])))
    assert set(out["accepted"]) == {"a","b"}
    assert out["rejected"] == []
    assert sunk == [("n1","a"),("n1","b")]


def test_process_batch_rejects_sensitive_and_does_not_sink():
    sunk = []
    out = process_batch("n1",
        [it("ok1"), it("bad1", division="ACCT"), it("bad2", content="my secret here")],
        cfg(), set(), lambda n,i: sunk.append(i["id"]))
    assert out["accepted"] == ["ok1"]
    reasons = {r["id"]: r["reason"] for r in out["rejected"]}
    assert reasons == {"bad1":"sensitive","bad2":"sensitive"}
    assert sunk == ["ok1"]  # sink NEVER called for rejected items (leak=0)


def test_process_batch_dedupes_against_seen_ids():
    out = process_batch("n1", [it("dup"), it("new")], cfg(), {"dup"},
                       lambda n,i: None)
    assert out["accepted"] == ["new"]
    assert out["rejected"] == [{"id":"dup","reason":"duplicate"}]


def test_process_batch_partial_failure_returns_both_lists():
    out = process_batch("n1",
        [it("a"), {"content":"missingid"}, it("c", content="")],
        cfg(), set(), lambda n,i: None)
    assert out["accepted"] == ["a"]
    assert sorted(r["reason"] for r in out["rejected"]) == ["empty","missing_id"]


# --- HTTP-level tests via the WSGI/http.server handler ---
def test_http_intake_rejects_bad_key(tmp_path):
    from brain_share.intake_server import make_app
    sunk = []
    app = make_app(cfg(), lambda n,i: sunk.append(i["id"]), lambda: set())
    body = json.dumps({"node_id":"n1","key":"WRONG","items":[it("a")]}).encode()
    status, resp = _call(app, body)
    assert status.startswith("401")
    assert sunk == []


def test_http_intake_accepts_good_key_and_returns_json(tmp_path):
    from brain_share.intake_server import make_app
    sunk = []
    app = make_app(cfg(), lambda n,i: sunk.append(i["id"]), lambda: set())
    body = json.dumps({"node_id":"n1","key":"k",
                       "items":[it("a"), it("bad", division="ACCT")]}).encode()
    status, resp = _call(app, body)
    assert status.startswith("200")
    out = json.loads(resp)
    assert out["accepted"] == ["a"]
    assert out["rejected"] == [{"id":"bad","reason":"sensitive"}]
    assert sunk == ["a"]


def test_http_intake_uses_constant_time_compare(monkeypatch):
    """Auth must use hmac.compare_digest, not == (timing attack)."""
    import brain_share.intake_server as srv
    src = open(srv.__file__, "r", encoding="utf-8").read()
    assert "compare_digest" in src


def test_http_intake_rejects_path_traversal_node_id():
    """POST with node_id=../etc should be rejected at HTTP layer (400)."""
    from brain_share.intake_server import make_app
    sunk = []
    app = make_app(cfg(), lambda n,i: sunk.append(i["id"]), lambda: set())
    body = json.dumps({"node_id":"../etc","key":"k",
                       "items":[it("a")]}).encode()
    status, resp = _call(app, body)
    assert status.startswith("400")
    assert sunk == []  # sink never called


def test_process_batch_rejects_invalid_item_id():
    """Item with id=../evil (path traversal) should be rejected, sink not called."""
    sunk = []
    out = process_batch("n1", [{"id":"../evil","content":"bad"}], cfg(),
                       set(), lambda n,i: sunk.append(i["id"]))
    assert out["accepted"] == []
    assert out["rejected"] == [{"id":"../evil","reason":"invalid_id"}]
    assert sunk == []  # sink never called for rejected item


def _call(app, body):
    """Minimal in-process WSGI invocation for tests."""
    captured = {}
    def start_response(status, headers):
        captured["status"] = status
    env = {"REQUEST_METHOD":"POST","PATH_INFO":"/intake",
           "CONTENT_LENGTH":str(len(body)),"wsgi.input":__import__("io").BytesIO(body)}
    result = b"".join(app(env, start_response))
    return captured["status"], result.decode("utf-8")
