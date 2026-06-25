import json
from pathlib import Path
import pytest

from brain_share.synth_daemon import SynthWatermark, discover_topics, synth_once


def _write(incoming_dir: Path, node, item):
    d = incoming_dir / node
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{item['id']}.json").write_text(
        json.dumps(item, ensure_ascii=False), encoding="utf-8")


def test_watermark_roundtrip(tmp_path):
    wm = SynthWatermark(str(tmp_path / "wm.db"))
    assert wm.last_seen("t1") is None
    wm.record("t1", "id-5")
    assert wm.last_seen("t1") == "id-5"
    wm.record("t1", "id-9")
    assert wm.last_seen("t1") == "id-9"


def test_discover_topics_groups_by_metadata_topic(tmp_path):
    inc = tmp_path / "incoming"
    _write(inc, "n1", {"id":"a","content":"x","metadata":{"topic":"auth"}})
    _write(inc, "n1", {"id":"b","content":"y","metadata":{"topic":"billing"}})
    _write(inc, "n2", {"id":"c","content":"z","metadata":{"topic":"auth"}})
    _write(inc, "n1", {"id":"d","content":"w"})  # no topic -> general
    groups = discover_topics(inc, topic_fn=None)
    assert set(groups) == {"auth","billing","general"}
    assert {i["id"] for i in groups["auth"]} == {"a","c"}
    assert {i["id"] for i in groups["general"]} == {"d"}


def test_synth_once_calls_llm_per_topic_and_writes_vault(tmp_path):
    inc = tmp_path / "incoming"
    vault = tmp_path / "obsidian"
    _write(inc, "n1", {"id":"a","content":"alpha","metadata":{"topic":"t1"}})
    _write(inc, "n1", {"id":"b","content":"beta","metadata":{"topic":"t1"}})

    calls = []
    def fake_llm(prompt):
        calls.append(prompt[:30])
        return "SYNTH BODY"
    def fake_extract(text):
        return ([], [])

    wm = SynthWatermark(str(tmp_path / "wm.db"))
    out = synth_once(inc, str(vault), wm, fake_llm, fake_extract,
                     updated="2026-06-25")
    assert out["topics_synthed"] == 1
    assert out["items_seen"] == 2
    # Vault file written via WikiStore (topic-named .md exists somewhere under vault)
    assert any(p.suffix == ".md" for p in vault.rglob("*"))
    # Watermark recorded
    assert wm.last_seen("t1") is not None


def test_synth_once_skips_when_no_new_items(tmp_path):
    inc = tmp_path / "incoming"
    _write(inc, "n1", {"id":"a","content":"alpha","metadata":{"topic":"t1"}})
    wm = SynthWatermark(str(tmp_path / "wm.db"))
    def llm(p): return "BODY"
    def ex(t): return ([], [])

    first = synth_once(inc, str(tmp_path/"v"), wm, llm, ex, updated="2026-06-25")
    second = synth_once(inc, str(tmp_path/"v"), wm, llm, ex, updated="2026-06-25")
    assert first["topics_synthed"] == 1
    assert second["topics_synthed"] == 0
    assert second["skipped"] >= 1


def test_synth_once_empty_incoming_returns_zero(tmp_path):
    wm = SynthWatermark(str(tmp_path / "wm.db"))
    out = synth_once(tmp_path / "incoming", str(tmp_path/"v"), wm,
                     lambda p:"", lambda t:([],[]), updated="2026-06-25")
    assert out == {"topics_synthed":0, "items_seen":0, "skipped":0}


def test_synth_once_does_not_advance_watermark_on_empty_llm(tmp_path):
    """If llm_fn returns empty string, WikiStore.upsert writes nothing and
    returns ""; the watermark MUST NOT advance, so the next pass retries
    instead of permanently skipping the topic."""
    inc = tmp_path / "incoming"
    _write(inc, "n1", {"id":"a","content":"alpha","metadata":{"topic":"t1"}})
    wm = SynthWatermark(str(tmp_path / "wm.db"))

    def empty_llm(prompt):
        return ""
    def ex(t):
        return ([], [])

    out = synth_once(inc, str(tmp_path/"v"), wm, empty_llm, ex,
                     updated="2026-06-25")
    assert out["topics_synthed"] == 0
    assert out["skipped"] >= 1
    assert wm.last_seen("t1") is None  # NOT advanced — retry possible

    # Second pass with a working LLM must now succeed (topic still pending).
    def good_llm(prompt): return "SYNTH BODY"
    out2 = synth_once(inc, str(tmp_path/"v"), wm, good_llm, ex,
                     updated="2026-06-25")
    assert out2["topics_synthed"] == 1
    assert wm.last_seen("t1") is not None
