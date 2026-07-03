#!/usr/bin/env python3
"""
healthcheck.py — Mokai Brain Kit 로컬 장기기억 진단기

로컬 PC에서 실행해 아래를 한 번에 점검한다 (전부 읽기 전용, 데이터 무손상):
  1. 메모리 루트 / chroma_db(RAG 저장소) / 옵시디언 볼트 존재 · 규모
  2. memory_config.py 의 wiki 컬렉션 패치 여부
  3. brain_share 모듈 · brain_share_config.json (read_key / blocked_divisions)
  4. RAG 서버(:9210) · 공유 게이트웨이(share_port, 기본 :9211) 살아있는지
  5. 스킬(~/.claude/skills) · 플러그인(~/.claude/plugins) 설치 여부
  6. 런타임 도구(graphify / yt-dlp / serena-agent) 설치 여부

사용:
  python healthcheck.py
  python healthcheck.py --root C:/brainkit/memory --claude-home C:/Users/이름/.claude
"""

import argparse
import json
import os
import shutil
import socket
import sys
import urllib.request
from pathlib import Path

OK, WARN, FAIL, INFO = "[OK]  ", "[WARN]", "[FAIL]", "[..]  "
results = []  # (status, label, detail)


def rec(status, label, detail=""):
    results.append((status, label, detail))
    print(f"  {status} {label}" + (f"  —  {detail}" if detail else ""))


def port_alive(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_json(url, payload, timeout=30.0):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Mokai Brain Kit 로컬 장기기억 진단")
    ap.add_argument("--root", default=r"C:\brainkit\memory",
                    help=r"메모리 루트 (기본 C:\brainkit\memory). bash면 슬래시 사용)")
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"),
                    help="Claude Code 홈 (기본 ~/.claude)")
    ap.add_argument("--rag-port", type=int, default=9210, help="RAG 서버 포트 (기본 9210)")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    claude_home = Path(args.claude_home).expanduser()

    print("=" * 64)
    print(f"Mokai Brain Kit 장기기억 헬스체크")
    print(f"  memory root : {root}")
    print(f"  claude home : {claude_home}")
    print("=" * 64)

    # ── 1. 메모리 루트 / RAG 저장소 / 옵시디언 ──────────────────────
    print("\n[1] 저장소 · RAG · 옵시디언")
    if not root.exists():
        rec(FAIL, "메모리 루트 없음", str(root) + " — --root 로 실제 경로 지정")
    else:
        rec(OK, "메모리 루트 존재")

    chroma = root / "chroma_db"
    if chroma.exists():
        nfiles = sum(1 for _ in chroma.rglob("*") if _.is_file())
        nsql = list(chroma.rglob("*.sqlite3")) + list(chroma.rglob("chroma.sqlite3"))
        rec(OK if nfiles else WARN, "chroma_db (RAG 벡터 저장소)",
            f"{nfiles} 파일" + (f", sqlite {len(nsql)}개" if nsql else ", sqlite 없음"))
    else:
        rec(FAIL, "chroma_db 없음", "RAG 저장소가 이 루트에 없음")

    # 옵시디언 볼트: config 의 vault_dir 우선, 없으면 관례 경로
    cfg_json = root / "brain_share_config.json"
    vault_dir = None
    cfg = {}
    if cfg_json.exists():
        try:
            cfg = json.loads(cfg_json.read_text(encoding="utf-8"))
            vault_dir = cfg.get("vault_dir") or None
        except Exception as e:
            rec(WARN, "brain_share_config.json 파싱 실패", str(e))
    vault_candidates = [p for p in [
        Path(vault_dir).expanduser() if vault_dir else None,
        root / "obsidian",
        root.parent / "obsidian",
    ] if p]
    vault = next((p for p in vault_candidates if p.exists()), None)
    if vault:
        nmd = sum(1 for _ in vault.rglob("*.md"))
        has_obs = (vault / ".obsidian").exists()
        rec(OK if nmd else WARN, "옵시디언 볼트",
            f"{vault}  —  {nmd}개 .md" + (", .obsidian 설정 있음" if has_obs else ", .obsidian 없음(볼트 아닐 수 있음)"))
    else:
        rec(WARN, "옵시디언 볼트 못 찾음",
            "확인한 경로: " + ", ".join(str(p) for p in vault_candidates))

    # ── 2. memory_config.py wiki 패치 ─────────────────────────────
    print("\n[2] memory_config.py (wiki 컬렉션)")
    mem_cfg = root / "memory_config.py"
    if mem_cfg.exists():
        txt = mem_cfg.read_text(encoding="utf-8", errors="replace")
        rec(OK if '"wiki"' in txt else WARN,
            "memory_config.py",
            "wiki 컬렉션 있음" if '"wiki"' in txt else "wiki 컬렉션 없음 — install.py 재실행 필요")
    else:
        rec(WARN, "memory_config.py 없음", "이 루트에 메모리 설정 파일 없음")

    # ── 3. brain_share 모듈 / config ──────────────────────────────
    print("\n[3] brain_share 모듈 · 설정")
    bs = root / "brain_share"
    if bs.exists():
        mods = list(bs.glob("*.py"))
        rec(OK if mods else FAIL, "brain_share/ 모듈", f"{len(mods)}개 .py")
    else:
        rec(FAIL, "brain_share/ 없음", "install.py 미실행")

    if cfg_json.exists():
        rk = cfg.get("read_key", "")
        rk_ok = bool(rk) and rk != "CHANGE-ME-INSTALL-TIME"
        rec(OK if rk_ok else FAIL, "read_key",
            "설정됨" if rk_ok else "미설정/기본값 — 게이트웨이 인증 불가")
        blocked = cfg.get("blocked_divisions", [])
        rec(OK if blocked else WARN, "blocked_divisions(누설 차단)",
            f"{blocked}" if blocked else "비어있음 — 민감 division 안 걸러짐(README 3~4단계)")
    else:
        rec(FAIL, "brain_share_config.json 없음", "install.py 미실행")

    # ── 4. 서버 살아있는지 ────────────────────────────────────────
    print("\n[4] 실행 중인 서버")
    if port_alive(args.host, args.rag_port):
        rec(OK, f"RAG 서버 :{args.rag_port}", "포트 응답")
        try:
            resp = http_json(f"http://{args.host}:{args.rag_port}/memory/search",
                             {"query": "healthcheck ping", "top_k": 1, "min_score": 0})
            n = len(resp.get("results", resp.get("matches", [])))
            rec(OK, "RAG 검색 응답", f"결과 {n}건 (읽기 정상, 최대 30s 대기)")
        except Exception as e:
            rec(WARN, "RAG 검색 실패", f"{type(e).__name__}: {e} (엔드포인트 다를 수 있음)")
    else:
        rec(WARN, f"RAG 서버 :{args.rag_port} 미응답", "RAG 서버 미기동이거나 다른 포트")

    share_port = int(cfg.get("share_port", 9211)) if cfg else 9211
    if port_alive(args.host, share_port):
        rec(OK, f"공유 게이트웨이 :{share_port}", "포트 응답")
    else:
        rec(WARN, f"공유 게이트웨이 :{share_port} 미응답",
            "gateway_mcp 미기동 (장기기억 저장/공유엔 필수는 아님)")

    # ── 5. 스킬 / 플러그인 ────────────────────────────────────────
    print("\n[5] 스킬 · 플러그인 (~/.claude)")
    skills_dir = claude_home / "skills"
    expected_skills = ["graphify", "karpathy-guidelines", "para-memory-files", "youtube-summary"]
    if skills_dir.exists():
        for s in expected_skills:
            has = (skills_dir / s / "SKILL.md").exists()
            rec(OK if has else WARN, f"skill: {s}", "설치됨" if has else "없음 — install_skills.py 재실행")
    else:
        rec(FAIL, "~/.claude/skills 없음", "install_skills.py 미실행 or --claude-home 경로 확인")

    plugins_dir = claude_home / "plugins"
    if plugins_dir.exists():
        found = [p.name for p in plugins_dir.rglob("*") if p.is_dir()]
        for pl in ["superpowers", "serena"]:
            has = any(pl in name.lower() for name in found)
            rec(OK if has else WARN, f"plugin: {pl}", "흔적 있음" if has else "폴더에서 못 찾음")
    else:
        rec(WARN, "~/.claude/plugins 없음", "plugins.zip 미병합")

    # ── 6. 런타임 도구 ────────────────────────────────────────────
    print("\n[6] 런타임 도구")
    rec(OK if shutil.which("graphify") else WARN, "graphify (PATH)",
        "있음" if shutil.which("graphify") else "PATH에 없음 — uv tool install graphifyy")
    for mod, label in [("yt_dlp", "yt-dlp"), ("serena", "serena-agent")]:
        try:
            __import__(mod)
            rec(OK, f"python: {label}", "import 가능")
        except Exception:
            rec(WARN, f"python: {label}", "미설치")

    # ── 요약 ──────────────────────────────────────────────────────
    n_fail = sum(1 for s, *_ in results if s == FAIL)
    n_warn = sum(1 for s, *_ in results if s == WARN)
    n_ok = sum(1 for s, *_ in results if s == OK)
    print("\n" + "=" * 64)
    print(f"요약:  OK {n_ok}  ·  WARN {n_warn}  ·  FAIL {n_fail}")
    if n_fail == 0 and n_warn == 0:
        print("→ 장기기억 파이프라인 전부 정상.")
    elif n_fail == 0:
        print("→ 핵심(저장소·RAG)은 정상. WARN 항목은 선택/보강 사항.")
    else:
        print("→ FAIL 항목부터 조치 필요 (위 detail 참고). README.md 설치 단계 확인.")
    print("=" * 64)
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
