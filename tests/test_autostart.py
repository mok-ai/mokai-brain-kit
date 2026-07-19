"""Tests for autostart.py (Windows HKCU Run helper)."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


class _FakeReg:
    """In-memory HKCU Run stand-in for tests."""
    def __init__(self):
        self.entries = {}

    def set(self, name, value):
        self.entries[name] = value

    def get(self, name):
        return self.entries.get(name)

    def delete(self, name):
        return self.entries.pop(name, None) is not None

    def enumerate(self):
        return dict(self.entries)


def test_register_writes_entry():
    from autostart import register
    r = _FakeReg()
    out = register("BrainKitSynthDaemon", r'wscript "C:\brainkit\start_synth.vbs"',
                   reg_backend=r)
    assert out == r'wscript "C:\brainkit\start_synth.vbs"'
    assert r.get("BrainKitSynthDaemon") == r'wscript "C:\brainkit\start_synth.vbs"'


def test_register_idempotent_same_value():
    from autostart import register
    r = _FakeReg()
    register("X", "cmd A", reg_backend=r)
    register("X", "cmd A", reg_backend=r)  # same value again
    assert r.enumerate() == {"X": "cmd A"}


def test_register_updates_when_value_changes():
    from autostart import register
    r = _FakeReg()
    register("X", "cmd A", reg_backend=r)
    register("X", "cmd B", reg_backend=r)
    assert r.get("X") == "cmd B"


def test_unregister_removes_entry():
    from autostart import register, unregister
    r = _FakeReg()
    register("X", "cmd", reg_backend=r)
    assert unregister("X", reg_backend=r) is True
    assert r.get("X") is None


def test_unregister_missing_returns_false():
    from autostart import unregister
    r = _FakeReg()
    assert unregister("ghost", reg_backend=r) is False


def test_list_entries_filters_to_brainkit_prefix():
    from autostart import list_entries
    r = _FakeReg()
    r.set("BrainKitIntake", "wscript A.vbs")
    r.set("BrainKitSynthDaemon", "wscript B.vbs")
    r.set("Slack", "slack.exe")
    r.set("OneDrive", "onedrive.exe")
    entries = list_entries(reg_backend=r)
    assert set(entries.keys()) == {"BrainKitIntake", "BrainKitSynthDaemon"}


def test_synth_daemon_has_cli_entry():
    """CLI entry lets `python -m brain_share.synth_daemon --config ...` run."""
    from brain_share import synth_daemon
    src = open(synth_daemon.__file__, "r", encoding="utf-8").read()
    assert 'if __name__ == "__main__":' in src
    assert "--config" in src and "--incoming" in src
