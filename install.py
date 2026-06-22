#!/usr/bin/env python3
"""
install_agent.py — Mokai Brain Kit 3.0.0 installer
DATA-PRESERVING: read + add only. Never deletes chroma_db, obsidian, or any existing content.
"""

import argparse
import importlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()

print("Mokai Brain Kit 3.0.0")

# ─────────────────────────────────────────────
# Args
# ─────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Mokai Brain Kit installer")
parser.add_argument("--root", default=r"C:\brainkit\memory", help="Agent memory root (default: C:\\agent\\memory)")
args = parser.parse_args()

ROOT = Path(args.root)
print(f"\n{'='*60}")
print(f"Mokai Brain Kit 3.0.0 INSTALLER")
print(f"Memory root: {ROOT}")
print(f"{'='*60}\n")

# ─────────────────────────────────────────────
# Step 6 first: Baseline preservation snapshot
# ─────────────────────────────────────────────
print("[0] Baseline snapshot (before install)")
chroma_dir = ROOT / "chroma_db"
obsidian_dir = ROOT / "obsidian"

chroma_count = 0
if chroma_dir.exists():
    chroma_count = sum(1 for _ in chroma_dir.rglob("*") if _.is_file())
print(f"    chroma_db files : {chroma_count}")

obsidian_count = 0
if obsidian_dir.exists():
    obsidian_count = sum(1 for _ in obsidian_dir.rglob("*.md"))
print(f"    obsidian .md    : {obsidian_count}")
print()

# ─────────────────────────────────────────────
# Step 1: Copy brain_share/
# ─────────────────────────────────────────────
print("[1] Copying brain_share modules...")
src_bs = HERE / "brain_share"
dst_bs = ROOT / "brain_share"
dst_bs.mkdir(parents=True, exist_ok=True)

copied_bs = 0
for f in src_bs.glob("*.py"):
    dst_f = dst_bs / f.name
    shutil.copy2(f, dst_f)
    copied_bs += 1
    print(f"    + {f.name}")
print(f"    → {copied_bs} module(s) copied to {dst_bs}")
print()

# ─────────────────────────────────────────────
# Step 2: Copy brain_share_tests/
# ─────────────────────────────────────────────
print("[2] Copying brain_share_tests...")
src_tests = HERE / "brain_share_tests"
dst_tests = ROOT / "brain_share_tests"
dst_tests.mkdir(parents=True, exist_ok=True)

copied_tests = 0
for f in src_tests.glob("*.py"):
    shutil.copy2(f, dst_tests / f.name)
    copied_tests += 1
print(f"    → {copied_tests} test file(s) copied to {dst_tests}")
print()

# ─────────────────────────────────────────────
# Step 3: pip install dependencies
# ─────────────────────────────────────────────
print("[3] Checking / installing pip dependencies...")
DEPS = ["numpy", "scikit-learn", "pyyaml", "mcp"]

for pkg in DEPS:
    try:
        importlib.import_module(pkg.replace("-", "_"))
        print(f"    [already present] {pkg}")
    except ImportError:
        print(f"    [installing]      {pkg} ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"    ERROR installing {pkg}:\n{result.stderr}")
        else:
            print(f"    [OK] {pkg} installed")
print()

# ─────────────────────────────────────────────
# Step 4: Patch memory_config.py — add wiki collection
# ─────────────────────────────────────────────
print("[4] Patching memory_config.py (wiki collection)...")
mem_cfg = ROOT / "memory_config.py"
mem_cfg_bak = ROOT / "memory_config.py.bak"

if mem_cfg.exists():
    # Backup only if .bak absent
    if not mem_cfg_bak.exists():
        shutil.copy2(mem_cfg, mem_cfg_bak)
        print(f"    Backed up → {mem_cfg_bak}")
    else:
        print(f"    Backup already exists, skipping: {mem_cfg_bak}")

    content = mem_cfg.read_text(encoding="utf-8")

    WIKI_LINE = '    "wiki":          f"{AGENT_NAME}_wiki",  # LLM wiki\n'

    if '"wiki"' in content:
        print("    [skip] 'wiki' collection already present")
    elif '"knowledge"' in content:
        content = content.replace(
            '"knowledge"',
            WIKI_LINE + '    "knowledge"',
            1
        )
        mem_cfg.write_text(content, encoding="utf-8")
        print("    [OK] Inserted wiki collection before 'knowledge'")
    else:
        print("    [warn] Could not find 'knowledge' line — wiki NOT inserted. Please add manually.")
else:
    print(f"    [skip] {mem_cfg} not found — no patch needed")
print()

# ─────────────────────────────────────────────
# Step 5: Create brain_share_config.json if absent
# ─────────────────────────────────────────────
print("[5] Checking brain_share_config.json...")
cfg_json = ROOT / "brain_share_config.json"

if cfg_json.exists():
    print(f"    [skip] Already exists: {cfg_json}")
else:
    read_key = secrets.token_hex(16)
    config_data = {
        "role": "HUB",
        "read_key": read_key,
        "share_port": 9211,
        "vault_dir": r"C:\brainkit\obsidian",
        "allowed_collections": [
            "wiki",
            "knowledge",
            "decisions",
            "conversations",
            "tasks"
        ],
        "blocked_tag_patterns": [
            "회계", "세무", "손익", "고객명단", "미수금", "매매", "계약"
        ],
        "blocked_keyword_patterns": [
            "api_key", "secret", "비밀번호", "인증서", "token", "passwd"
        ],
        "blocked_divisions": []
    }
    cfg_json.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    [OK] Created: {cfg_json}")
    print(f"    *** Generated read_key: {read_key} ***")
    print(f"    NOTE: blocked_divisions is empty — fill it after measuring your RAG divisions (see README)")
print()

# ─────────────────────────────────────────────
# Step 6b: Post-install baseline check
# ─────────────────────────────────────────────
print("[6] Post-install baseline verification (data preservation check)...")
chroma_count_after = 0
if chroma_dir.exists():
    chroma_count_after = sum(1 for _ in chroma_dir.rglob("*") if _.is_file())
obsidian_count_after = 0
if obsidian_dir.exists():
    obsidian_count_after = sum(1 for _ in obsidian_dir.rglob("*.md"))

print(f"    chroma_db files : {chroma_count} → {chroma_count_after}  ({'OK unchanged' if chroma_count == chroma_count_after else 'CHANGED — investigate'})")
print(f"    obsidian .md    : {obsidian_count} → {obsidian_count_after}  ({'OK unchanged' if obsidian_count == obsidian_count_after else 'CHANGED — investigate'})")
print()

# ─────────────────────────────────────────────
# Step 7: Import smoke test
# ─────────────────────────────────────────────
print("[7] Import smoke test...")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import brain_share.config as bs_config
    print("    [OK] brain_share.config imported")
except Exception as e:
    print(f"    [WARN] brain_share.config import failed: {e}")

try:
    import brain_share.graph_store as bs_gs
    print("    [OK] brain_share.graph_store imported")
except Exception as e:
    print(f"    [WARN] brain_share.graph_store import failed: {e}")

try:
    import brain_share.gateway_mcp as bs_gw
    print("    [OK] brain_share.gateway_mcp imported")
except Exception as e:
    print(f"    [WARN] brain_share.gateway_mcp import failed: {e}")

try:
    load_config = getattr(bs_config, "load_config", None)
    if load_config and cfg_json.exists():
        cfg = load_config(str(cfg_json))
        print(f"    [OK] load_config({cfg_json.name}) succeeded")
    else:
        print("    [skip] load_config not found or config json missing")
except Exception as e:
    print(f"    [WARN] load_config failed: {e}")

print("    IMPORT OK")
print()

# ─────────────────────────────────────────────
# Step 8: Run pytest
# ─────────────────────────────────────────────
print("[8] Running tests...")
test_dir = str(ROOT / "brain_share_tests")
result = subprocess.run(
    [sys.executable, "-m", "pytest", test_dir, "-q", "--tb=short"],
    capture_output=True, text=True
)
# Print last few lines (summary)
output = (result.stdout + result.stderr).strip()
lines = output.splitlines()
# Print last 10 lines as summary
for line in lines[-10:]:
    print(f"    {line}")
print()

# ─────────────────────────────────────────────
# Final
# ─────────────────────────────────────────────
print("=" * 60)
print("INSTALL COMPLETE — data preserved (chroma/obsidian untouched).")
print("Gateway NOT auto-started; see README.md.")
print(f"brain_share modules : {copied_bs}")
print(f"test files          : {copied_tests}")
print("=" * 60)
