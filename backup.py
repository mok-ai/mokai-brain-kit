#!/usr/bin/env python3
"""backup.py — Mokai Brain Kit daily snapshot + generational rotation.

Snapshots (read-only) the following under <backups_dir>/YYYY-MM-DD/:
  - chroma_db.zip           (from <root>/chroma_db)
  - obsidian.zip            (from <root_parent>/obsidian if present, else <root>/obsidian)
  - brain_share_config.json (copy)
  - memory_config.py        (copy)
  - LEAF_REGISTRATION.md    (copy)
  - manifest.json           (date, root, per-file sha256 + size)

Old snapshots (older than keep_days from today) are pruned.

CLI:
  python backup.py --root C:/brainkit/memory [--backups <dir>] [--keep-days 7]
"""
import argparse
import datetime
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

OPTIONAL_FILES = ("brain_share_config.json", "memory_config.py", "LEAF_REGISTRATION.md")


def _zip_dir(src: Path, out_zip: Path):
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src).as_posix())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_vault(root: Path) -> Path:
    for cand in (root.parent / "obsidian", root / "obsidian"):
        if cand.exists():
            return cand
    return root.parent / "obsidian"  # nominal (may not exist)


def create_backup(root, backups_dir, keep_days: int = 7,
                  today: str = None) -> dict:
    root = Path(root); backups_dir = Path(backups_dir)
    if today is None:
        today = datetime.date.today().isoformat()
    day = backups_dir / today
    day.mkdir(parents=True, exist_ok=True)

    manifest = {"date": today, "root": str(root), "files": {}}

    chroma_src = root / "chroma_db"
    chroma_zip = day / "chroma_db.zip"
    if chroma_src.exists():
        _zip_dir(chroma_src, chroma_zip)
    else:
        # still write empty zip so restore layout is predictable
        with zipfile.ZipFile(chroma_zip, "w", zipfile.ZIP_DEFLATED):
            pass
    manifest["files"]["chroma_db.zip"] = {
        "sha256": _sha256(chroma_zip), "size": chroma_zip.stat().st_size}

    vault_src = _resolve_vault(root)
    obs_zip = day / "obsidian.zip"
    if vault_src.exists():
        _zip_dir(vault_src, obs_zip)
    else:
        with zipfile.ZipFile(obs_zip, "w", zipfile.ZIP_DEFLATED):
            pass
    manifest["files"]["obsidian.zip"] = {
        "sha256": _sha256(obs_zip), "size": obs_zip.stat().st_size}

    for name in OPTIONAL_FILES:
        src = root / name
        if src.exists():
            dst = day / name
            shutil.copy2(src, dst)
            manifest["files"][name] = {"sha256": _sha256(dst), "size": dst.stat().st_size}

    (day / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    pruned = _prune_old(backups_dir, today, keep_days)
    return {
        "backup_dir": str(day),
        "kept": keep_days,
        "pruned": pruned,
        "manifest": manifest,
    }


def _prune_old(backups_dir: Path, today: str, keep_days: int) -> list:
    """Remove day-dirs whose date is older than keep_days-1 behind today.
    Keeps today. Non-date-named dirs are ignored."""
    try:
        cutoff = datetime.date.fromisoformat(today) - datetime.timedelta(days=keep_days - 1)
    except Exception:
        return []
    pruned = []
    if not backups_dir.exists():
        return pruned
    for p in backups_dir.iterdir():
        if not p.is_dir():
            continue
        try:
            d = datetime.date.fromisoformat(p.name)
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(p, ignore_errors=True)
            pruned.append(p.name)
    return sorted(pruned)


def main():
    ap = argparse.ArgumentParser(description="Mokai Brain Kit daily backup")
    ap.add_argument("--root", default=r"C:\brainkit\memory")
    ap.add_argument("--backups", default=None,
                    help="Backup destination (default: <root>/backups)")
    ap.add_argument("--keep-days", type=int, default=7)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    backups = Path(args.backups).resolve() if args.backups else (root / "backups")
    out = create_backup(root, backups, keep_days=args.keep_days)
    print(f"[OK] backup -> {out['backup_dir']}")
    if out["pruned"]:
        print(f"    pruned {len(out['pruned'])}: {out['pruned']}")


if __name__ == "__main__":
    main()
