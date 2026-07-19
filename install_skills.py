#!/usr/bin/env python3
"""
install_skills.py — Mokai Brain Kit skill bundle installer
ADDITIVE only: never deletes existing skills or plugin directories.
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

print("Mokai Brain Kit 3.3.0")


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

    # 2. Merge plugins
    print("[2/3] Merging plugins...")
    plugins_ok = merge_plugins(here / "plugins.zip", claude_home)
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
    print(f"Plugins merged : {'OK' if plugins_ok else 'FAILED/SKIPPED'}")
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
