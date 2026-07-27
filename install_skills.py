#!/usr/bin/env python3
"""
install_skills.py — Mokai Brain Kit skill bundle installer
ADDITIVE only: never deletes existing skills or plugin directories.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

print("Mokai Brain Kit 3.5.0")


def copy_skills(skills_src: Path, claude_home: Path) -> list[str]:
    """Copy each skill folder into <claude-home>/skills/, overwriting that skill only."""
    skills_dst = claude_home / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)

    copied = []
    if not skills_src.is_dir():
        print(f"  [WARN] skills/ directory not found at {skills_src}")
        return copied

    for skill_dir in sorted(skills_src.iterdir()):
        if not skill_dir.is_dir():
            continue
        dst = skills_dst / skill_dir.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(skill_dir, dst, ignore=shutil.ignore_patterns("__pycache__"))
        print(f"  [skill] {skill_dir.name} -> {dst}")
        copied.append(skill_dir.name)

    return copied


def merge_plugins(plugins_zip: Path, claude_home: Path) -> bool:
    """Unzip plugins.zip into <claude-home>/ so plugins/ tree merges in.
    If <claude-home>/plugins already exists, merge/overwrite files only (no wipe)."""
    if not plugins_zip.is_file():
        print(f"  [WARN] plugins.zip not found at {plugins_zip}")
        return False

    plugins_dst = claude_home / "plugins"
    print(f"  [plugins] Merging {plugins_zip.name} -> {claude_home}/")
    with zipfile.ZipFile(plugins_zip, "r") as zf:
        for member in zf.namelist():
            # Extract to claude_home so plugins/ subtree merges
            zf.extract(member, claude_home)
    print(f"  [plugins] Merge complete -> {plugins_dst}")
    return True


def plan_registry(cache_root: str, found, existing: dict) -> dict:
    """Build installed_plugins.json content for THIS machine.

    The bundle deliberately ships no installed_plugins.json: that file stores
    absolute installPaths, and baking the build machine's paths into a public
    package leaked a personal account path for eleven releases (fixed 3.5.0)
    and was wrong on every other machine anyway. So the installer regenerates
    it here from the cache tree it just unpacked.

    Pure function. `found` is [(marketplace, plugin, version), ...].
    Entries for plugins we did NOT ship are preserved untouched — this is an
    additive installer, not a replacement.
    """
    out = dict(existing.get("plugins") or {})
    stamp = _now_iso()
    for market, plug, version in found:
        key = f"{plug}@{market}"
        prev = out.get(key) or [{}]
        first = prev[0] if isinstance(prev, list) and prev else {}
        out[key] = [{
            "scope": "user",
            "installPath": str(Path(cache_root) / market / plug / version),
            "version": version,
            "installedAt": first.get("installedAt", stamp),
            "lastUpdated": stamp,
        }]
    merged = dict(existing)
    merged["version"] = existing.get("version", 2)
    merged["plugins"] = out
    return merged


def plan_marketplaces(marketplaces_root: str, shipped: dict,
                      existing: dict) -> dict:
    """Fill installLocation (machine-local) into shipped marketplace meta,
    keeping any marketplace the user already had."""
    merged = dict(existing)
    for name, meta in (shipped or {}).items():
        entry = dict(merged.get(name) or {})
        entry.update(meta)
        entry["installLocation"] = str(Path(marketplaces_root) / name)
        merged[name] = entry
    return merged


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def scan_cache(cache_root: Path):
    """[(marketplace, plugin, version)] for every plugin dir under cache."""
    found = []
    if not cache_root.is_dir():
        return found
    for market in sorted(p for p in cache_root.iterdir() if p.is_dir()):
        for plug in sorted(p for p in market.iterdir() if p.is_dir()):
            for ver in sorted(p for p in plug.iterdir() if p.is_dir()):
                found.append((market.name, plug.name, ver.name))
    return found


def _read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def register_plugins(claude_home: Path) -> int:
    """Regenerate installed_plugins.json / known_marketplaces.json with paths
    local to this machine. Returns how many plugins were registered."""
    plugins_dir = claude_home / "plugins"
    cache_root = plugins_dir / "cache"
    found = scan_cache(cache_root)
    if not found:
        print("  [WARN] no plugin cache found — nothing to register")
        return 0

    reg_path = plugins_dir / "installed_plugins.json"
    reg = plan_registry(str(cache_root), found, _read_json(reg_path))
    reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    km_path = plugins_dir / "known_marketplaces.json"
    shipped = _read_json(km_path)
    km = plan_marketplaces(str(plugins_dir / "marketplaces"), shipped,
                           _read_json(km_path))
    km_path.write_text(json.dumps(km, ensure_ascii=False, indent=2),
                       encoding="utf-8")

    for market, plug, ver in found:
        print(f"  [reg] {plug}@{market} [{ver}]")
    return len(found)


def run_best_effort(cmd: list[str], label: str) -> bool:
    """Run a shell command, print success/fail, never abort on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print(f"  [OK]   {label}")
            return True
        else:
            print(f"  [FAIL] {label}")
            if result.stderr.strip():
                print(f"         {result.stderr.strip()[:200]}")
            return False
    except FileNotFoundError:
        print(f"  [FAIL] {label} — command not found: {cmd[0]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] {label} — timed out after 120s")
        return False
    except Exception as e:
        print(f"  [FAIL] {label} — {e}")
        return False


def install_tools() -> dict[str, bool]:
    """Install runtime dependencies (best-effort). Returns {name: success}."""
    results = {}

    # graphify: uv tool install graphifyy
    uv_path = shutil.which("uv")
    if uv_path:
        results["graphify (graphifyy)"] = run_best_effort(
            ["uv", "tool", "install", "graphifyy"],
            "uv tool install graphifyy"
        )
    else:
        print(
            "  [NOTE] `uv` not found — cannot install graphifyy.\n"
            "         Install uv first: pip install uv\n"
            "         Then re-run: uv tool install graphifyy\n"
            "         Also note: uv may require `uv python install` before first use."
        )
        results["graphify (graphifyy)"] = False

    # youtube-summary: yt-dlp
    results["youtube-summary (yt-dlp)"] = run_best_effort(
        [sys.executable, "-m", "pip", "install", "yt-dlp"],
        "pip install yt-dlp"
    )

    # serena: serena-agent
    results["serena (serena-agent)"] = run_best_effort(
        [sys.executable, "-m", "pip", "install", "serena-agent"],
        "pip install serena-agent"
    )
    print(
        "  [NOTE] serena MCP must be registered separately after pip install.\n"
        "         Options:\n"
        "           a) The plugins.zip marketplace may auto-register it.\n"
        "           b) Or run:  claude mcp add serena-agent\n"
        "           c) Or add to ~/.claude.json > mcpServers manually.\n"
        "         See SKILLS_README.md for details."
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Install Mokai Brain Kit skill bundle into Claude Code home directory."
    )
    parser.add_argument(
        "--claude-home",
        default=os.path.expanduser("~/.claude"),
        help="Path to Claude Code home directory (default: ~/.claude)",
    )
    args = parser.parse_args()

    here = Path(__file__).parent.resolve()
    claude_home = Path(args.claude_home).resolve()

    print(f"\n=== Mokai Brain Kit Skill Bundle Installer ===")
    print(f"Source : {here}")
    print(f"Target : {claude_home}")
    print()

    # 1. Copy skills
    print("[1/3] Copying skills...")
    skills_copied = copy_skills(here / "skills", claude_home)
    print()

    # 2. Merge plugins, then register them with paths local to THIS machine
    print("[2/3] Merging plugins...")
    plugins_ok = merge_plugins(here / "plugins.zip", claude_home)
    registered = register_plugins(claude_home) if plugins_ok else 0
    print()

    # 3. Install runtime tools
    print("[3/3] Installing runtime tools (best-effort)...")
    tool_results = install_tools()
    print()

    # Final summary
    print("=" * 45)
    print("SUMMARY")
    print("=" * 45)
    print(f"Skills copied  : {len(skills_copied)}")
    for s in skills_copied:
        print(f"  - {s}")
    print(f"Plugins merged : {'OK' if plugins_ok else 'FAILED/SKIPPED'}"
          f"  (registered {registered})")
    print("Tools:")
    for name, ok in tool_results.items():
        status = "OK" if ok else "FAILED/SKIPPED"
        print(f"  [{status}] {name}")
    print()
    print("ACTION REQUIRED:")
    print("  1. Restart Claude Code to load new skills.")
    print("  2. Verify serena MCP is registered (see NOTE above).")
    print("  3. Add graphify to PATH if uv tool install succeeded.")
    print("=" * 45)


if __name__ == "__main__":
    main()
