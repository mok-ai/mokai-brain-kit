import json, sqlite3, os
from pathlib import Path
import pytest

# The two utils sit at the zip top-level, not in brain_share/. Tests add
# that dir to sys.path so `import backup` / `import restore` works.
import sys
_ROOT = Path(__file__).resolve().parent.parent  # upgrade_package_epikx/
sys.path.insert(0, str(_ROOT))


def _make_fake_root(tmp_path: Path):
    root = tmp_path / "memory"; root.mkdir()
    chroma = root / "chroma_db"; chroma.mkdir()
    (chroma / "chroma.sqlite3").write_bytes(b"SQLITE_FAKE_HEADER" + b"\x00" * 100)
    (chroma / "index").mkdir()
    (chroma / "index" / "data.bin").write_bytes(b"DATA")
    obs = root.parent / "obsidian" / "MEMORY"
    obs.mkdir(parents=True)
    (obs / "topic_00.md").write_text("# alpha\ncontent A", encoding="utf-8")
    (obs / "topic_01.md").write_text("# beta\ncontent B", encoding="utf-8")
    (root / "brain_share_config.json").write_text(
        json.dumps({"role":"HUB","read_key":"kkk"}), encoding="utf-8")
    (root / "memory_config.py").write_text("COLLECTIONS = {}\n", encoding="utf-8")
    (root / "LEAF_REGISTRATION.md").write_text("# leaf reg\n", encoding="utf-8")
    return root


def test_create_backup_writes_expected_layout(tmp_path):
    from backup import create_backup
    root = _make_fake_root(tmp_path)
    backups = tmp_path / "backups"
    out = create_backup(root, backups, keep_days=7, today="2026-07-19")
    day = backups / "2026-07-19"
    assert day.exists()
    assert (day / "chroma_db.zip").exists()
    assert (day / "obsidian.zip").exists()
    assert (day / "brain_share_config.json").exists()
    assert (day / "memory_config.py").exists()
    assert (day / "LEAF_REGISTRATION.md").exists()
    manifest = json.loads((day / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["date"] == "2026-07-19"
    assert manifest["root"] == str(root)
    assert manifest["files"]["chroma_db.zip"]["sha256"]
    assert out["backup_dir"] == str(day)


def test_create_backup_prunes_beyond_keep_days(tmp_path):
    from backup import create_backup
    root = _make_fake_root(tmp_path)
    backups = tmp_path / "backups"
    # Pre-seed a mix: recent (within window) and old (outside window)
    # With keep_days=7 and today=2026-07-19, cutoff is 2026-07-13.
    # Keep: 2026-07-13 and later. Prune: 2026-07-12 and earlier.
    for d in ["2026-07-01","2026-07-05","2026-07-10","2026-07-13","2026-07-15","2026-07-17"]:
        (backups / d).mkdir(parents=True)
    out = create_backup(root, backups, keep_days=7, today="2026-07-19")
    # After prune, only backups >= cutoff (2026-07-13) remain
    remaining = sorted(p.name for p in backups.iterdir() if p.is_dir())
    assert "2026-07-19" in remaining
    assert "2026-07-17" in remaining
    assert "2026-07-15" in remaining
    assert "2026-07-13" in remaining
    # Everything before cutoff must be gone
    assert "2026-07-10" not in remaining
    assert "2026-07-05" not in remaining
    assert "2026-07-01" not in remaining
    assert set(out["pruned"]) == {"2026-07-01","2026-07-05","2026-07-10"}


def test_create_backup_missing_optional_files_still_succeeds(tmp_path):
    from backup import create_backup
    root = tmp_path / "memory"; root.mkdir()
    (root / "chroma_db").mkdir()  # empty chroma OK
    out = create_backup(root, tmp_path / "backups", keep_days=7, today="2026-07-19")
    day = Path(out["backup_dir"])
    assert (day / "chroma_db.zip").exists()
    assert not (day / "brain_share_config.json").exists()  # skipped, not error
    assert (day / "manifest.json").exists()


def test_restore_dry_run_lists_files_without_writing(tmp_path):
    from backup import create_backup
    from restore import restore_backup
    root = _make_fake_root(tmp_path)
    backups = tmp_path / "backups"
    create_backup(root, backups, keep_days=7, today="2026-07-19")
    # Mutate current state (simulate later corruption)
    (root / "brain_share_config.json").write_text('{"role":"CORRUPTED"}', encoding="utf-8")
    out = restore_backup(root, backups, "2026-07-19", confirm=False)
    assert out["restored"] == []
    assert "chroma_db.zip" in out["planned"]
    assert "brain_share_config.json" in out["planned"]
    # Confirm the config was NOT touched
    assert '"CORRUPTED"' in (root / "brain_share_config.json").read_text(encoding="utf-8")


def test_restore_with_confirm_replaces_files(tmp_path):
    from backup import create_backup
    from restore import restore_backup
    root = _make_fake_root(tmp_path)
    backups = tmp_path / "backups"
    create_backup(root, backups, keep_days=7, today="2026-07-19")
    # Delete a file + corrupt another
    (root / "chroma_db" / "chroma.sqlite3").unlink()
    (root / "brain_share_config.json").write_text('{"corrupt":true}', encoding="utf-8")
    out = restore_backup(root, backups, "2026-07-19", confirm=True)
    assert "chroma_db.zip" in out["restored"]
    assert "brain_share_config.json" in out["restored"]
    # File contents match original
    cfg = json.loads((root / "brain_share_config.json").read_text(encoding="utf-8"))
    assert cfg["role"] == "HUB"
    assert (root / "chroma_db" / "chroma.sqlite3").exists()


def test_restore_missing_date_raises(tmp_path):
    from restore import restore_backup
    with pytest.raises(FileNotFoundError):
        restore_backup(tmp_path / "memory", tmp_path / "backups",
                       "2999-01-01", confirm=True)


def test_prune_removes_backups_older_than_cutoff_date(tmp_path):
    """date-cutoff retention: PC-off gap simulation. Only date-based cutoff
    counts, not rank; snapshots older than keep_days from today go away
    even if that leaves fewer than keep_days total."""
    from backup import create_backup
    root = _make_fake_root(tmp_path)
    backups = tmp_path / "backups"
    # Pre-seed a scattered set: mostly OLD, one recent
    for d in ["2026-06-01","2026-06-15","2026-07-10","2026-07-15"]:
        (backups / d).mkdir(parents=True)
    out = create_backup(root, backups, keep_days=7, today="2026-07-19")
    remaining = sorted(p.name for p in backups.iterdir() if p.is_dir())
    # cutoff = 2026-07-13. Keep: 07-19 (today), 07-15. Prune everything older.
    assert "2026-07-19" in remaining
    assert "2026-07-15" in remaining
    assert "2026-07-10" not in remaining  # < cutoff
    assert "2026-06-15" not in remaining
    assert "2026-06-01" not in remaining
    assert set(out["pruned"]) == {"2026-06-01","2026-06-15","2026-07-10"}


def test_zip_sha_stable_across_repeat_runs(tmp_path):
    """Sorted rglob → same source content produces same zip SHA on repeat."""
    from backup import create_backup
    import hashlib
    root = _make_fake_root(tmp_path)
    backups1 = tmp_path / "backups1"
    backups2 = tmp_path / "backups2"
    create_backup(root, backups1, keep_days=7, today="2026-07-19")
    create_backup(root, backups2, keep_days=7, today="2026-07-19")
    sha1 = hashlib.sha256((backups1 / "2026-07-19" / "chroma_db.zip").read_bytes()).hexdigest()
    sha2 = hashlib.sha256((backups2 / "2026-07-19" / "chroma_db.zip").read_bytes()).hexdigest()
    assert sha1 == sha2, "chroma_db.zip SHA differs across identical-content runs — determinism regression"
    # Also verify obsidian.zip
    sha1_o = hashlib.sha256((backups1 / "2026-07-19" / "obsidian.zip").read_bytes()).hexdigest()
    sha2_o = hashlib.sha256((backups2 / "2026-07-19" / "obsidian.zip").read_bytes()).hexdigest()
    assert sha1_o == sha2_o
