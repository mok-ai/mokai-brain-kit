#!/usr/bin/env python3
"""restore.py — Restore a Mokai Brain Kit snapshot produced by backup.py.

Dry-run by default (prints what WOULD change). Actual restore requires --yes.

Restore behavior:
  - chroma_db.zip -> extracted over <root>/chroma_db (existing files replaced)
  - obsidian.zip  -> extracted over the resolved vault dir
  - individual .json/.py/.md files copied over <root>/<name>

CLI:
  python restore.py --root C:/brainkit/memory --date 2026-07-19 [--yes]
"""
import argparse
import datetime
import shutil
import sys
import zipfile
from pathlib import Path

OPTIONAL_FILES = ("brain_share_config.json", "memory_config.py", "LEAF_REGISTRATION.md")


def _resolve_vault(root: Path) -> Path:
    for cand in (root.parent / "obsidian", root / "obsidian"):
        if cand.exists():
            return cand
    return root.parent / "obsidian"


def _unzip_over(src_zip: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src_zip, "r") as z:
        z.extractall(dst_dir)


def restore_backup(root, backups_dir, date: str, *, confirm: bool = False) -> dict:
    root = Path(root); backups_dir = Path(backups_dir)
    day = backups_dir / date
    if not day.exists():
        raise FileNotFoundError(f"No backup found for {date}: {day}")

    planned = []
    for entry in day.iterdir():
        if entry.name == "manifest.json":
            continue
        planned.append(entry.name)

    if not confirm:
        return {"restored": [], "planned": sorted(planned), "confirmed": False}

    restored = []
    for name in planned:
        src = day / name
        if name == "chroma_db.zip":
            _unzip_over(src, root / "chroma_db")
        elif name == "obsidian.zip":
            _unzip_over(src, _resolve_vault(root))
        elif name in OPTIONAL_FILES:
            shutil.copy2(src, root / name)
        else:
            continue  # unknown, skip
        restored.append(name)
    return {"restored": sorted(restored), "planned": sorted(planned), "confirmed": True}


def main():
    ap = argparse.ArgumentParser(description="Mokai Brain Kit snapshot restore")
    ap.add_argument("--root", default=r"C:\brainkit\memory")
    ap.add_argument("--backups", default=None)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (must exist)")
    ap.add_argument("--yes", action="store_true",
                    help="Confirm actual restore (default: dry-run)")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    backups = Path(args.backups).resolve() if args.backups else (root / "backups")
    try:
        out = restore_backup(root, backups, args.date, confirm=args.yes)
    except FileNotFoundError as e:
        print(f"[FAIL] {e}"); sys.exit(2)
    if not out["confirmed"]:
        print(f"[DRY-RUN] would restore from {backups / args.date}:")
        for f in out["planned"]:
            print(f"    - {f}")
        print("Re-run with --yes to actually restore.")
    else:
        print(f"[OK] restored {len(out['restored'])} entries from {args.date}:")
        for f in out["restored"]:
            print(f"    - {f}")


if __name__ == "__main__":
    main()
