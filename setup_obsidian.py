#!/usr/bin/env python3
"""
setup_obsidian.py — 옵시디언 볼트 생성 + brain_share 연결

로컬 PC에서 한 번 실행하면:
  1. brain_share_config.json 의 vault_dir 확인/설정 (없으면 <root상위>/obsidian)
  2. 그 위치에 옵시디언 볼트 생성 (.obsidian/app.json 포함 → 앱이 볼트로 인식)
  3. 안내용 인덱스 페이지 작성
  4. (--seed) 실행 중인 RAG(:9210)에서 실제 기억을 읽어 브라우징용 노트로 채움
     → RAG는 읽기만 함(무손상). 노트는 볼트의 '_RAG_스냅샷' 폴더에만 생성.

기존 데이터(chroma_db/기존 .md)는 절대 삭제·수정하지 않음. 추가만 함.

사용:
  py setup_obsidian.py --root C:/smurfs/memory
  py setup_obsidian.py --root C:/smurfs/memory --seed          # RAG 기억으로 채우기
  py setup_obsidian.py --root C:/smurfs/memory --vault C:/smurfs/obsidian --seed
"""

import argparse
import json
import re
import socket
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MINIMAL_APP_JSON = {"promptDelete": False, "alwaysUpdateLinks": True}


def port_alive(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def rag_search(host, port, query, top_k=50, timeout=30.0):
    url = f"http://{host}:{port}/memory/search"
    body = json.dumps({"query": query, "top_k": top_k, "min_score": 0}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("results", data.get("matches", []))


def safe_name(s, maxlen=60):
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:maxlen] or "untitled").strip()


def main():
    ap = argparse.ArgumentParser(description="옵시디언 볼트 생성 + brain_share 연결")
    ap.add_argument("--root", default=r"C:\smurfs\memory", help="메모리 루트 (bash면 슬래시)")
    ap.add_argument("--vault", default=None, help="볼트 경로 강제 지정 (기본: config vault_dir 또는 <root상위>/obsidian)")
    ap.add_argument("--seed", action="store_true", help="RAG 기억을 브라우징 노트로 채움 (읽기 전용)")
    ap.add_argument("--rag-port", type=int, default=9210)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--seed-count", type=int, default=50, help="채울 기억 개수 상한 (기본 50)")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    root = Path(args.root).expanduser()
    cfg_path = root / "brain_share_config.json"

    print("=" * 60)
    print("옵시디언 볼트 설정")
    print(f"  메모리 루트 : {root}")
    print("=" * 60)

    if not root.exists():
        print(f"[FAIL] 메모리 루트 없음: {root}  — --root 로 실제 경로 지정")
        sys.exit(2)

    # ── 1. config 로드 + vault_dir 결정 ─────────────────────────
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] config 파싱 실패({e}) — 새로 만들지 않고 vault만 세팅")
    else:
        print(f"[WARN] {cfg_path} 없음 — vault_dir 만 파일에 기록")

    if args.vault:
        vault = Path(args.vault).expanduser()
    elif cfg.get("vault_dir"):
        vault = Path(cfg["vault_dir"]).expanduser()
    else:
        vault = root.parent / "obsidian"
    print(f"  볼트 경로   : {vault}")

    # ── 2. 볼트 폴더 + .obsidian 생성 ───────────────────────────
    vault.mkdir(parents=True, exist_ok=True)
    obs = vault / ".obsidian"
    obs.mkdir(exist_ok=True)
    app_json = obs / "app.json"
    if not app_json.exists():
        app_json.write_text(json.dumps(MINIMAL_APP_JSON, indent=2), encoding="utf-8")
        print(f"  [OK] 볼트 인식 파일 생성: {app_json}")
    else:
        print(f"  [skip] 이미 볼트임: {app_json}")

    # ── 3. 인덱스 페이지 ────────────────────────────────────────
    index = vault / "_브레인킷_위키.md"
    if not index.exists():
        index.write_text(
            f"---\ntopic: 브레인킷 위키 안내\nupdated: {now}\n---\n"
            "# 🧠 브레인킷 위키 볼트\n\n"
            "이 폴더는 brain_share 의 LLM 위키가 저장되는 옵시디언 볼트입니다.\n\n"
            "- `<division>/<주제>.md` : 에이전트가 RAG 기억을 요약해 만드는 정본 위키 페이지\n"
            "- `_RAG_스냅샷/` : (`--seed` 실행 시) 현재 RAG 장기기억을 그대로 훑어본 스냅샷\n\n"
            "위키 페이지는 에이전트가 주제를 합성할 때 자동으로 쌓입니다.\n",
            encoding="utf-8")
        print(f"  [OK] 인덱스 페이지: {index}")

    # ── 4. config 에 vault_dir 기록 (백업 후) ──────────────────
    if cfg_path.exists():
        cur = cfg.get("vault_dir", "")
        if cur != str(vault):
            bak = cfg_path.with_suffix(".json.bak")
            if not bak.exists():
                bak.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"  [OK] config 백업: {bak}")
            cfg["vault_dir"] = str(vault)
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  [OK] config.vault_dir = {vault}")
        else:
            print(f"  [skip] config.vault_dir 이미 일치")

    # ── 5. (선택) RAG 기억으로 스냅샷 채우기 ────────────────────
    if args.seed:
        print("\n[seed] RAG 장기기억 → 브라우징 노트")
        if not port_alive(args.host, args.rag_port):
            print(f"  [FAIL] RAG 서버 :{args.rag_port} 미응답 — 서버 켜고 다시 --seed")
        else:
            snap = vault / "_RAG_스냅샷"
            snap.mkdir(exist_ok=True)
            # 도메인 폭넓게 긁기 위한 다각도 질의 (임베딩 검색이라 '*'는 안 통함)
            queries = ["회사 정체성 소개", "마케팅 광고 성과", "AEO SEO 검색최적화",
                       "업무 규칙 지침", "제품 서비스 정보", "고객 프로젝트",
                       "의사결정 전략", "일정 계획 작업"]
            seen, written = set(), 0
            for q in queries:
                if written >= args.seed_count:
                    break
                try:
                    for r in rag_search(args.host, args.rag_port, q,
                                        top_k=min(20, args.seed_count)):
                        rid = r.get("id") or ""
                        if rid in seen or written >= args.seed_count:
                            continue
                        seen.add(rid)
                        content = (r.get("content") or "").strip()
                        if not content:
                            continue
                        meta = r.get("metadata", {}) or {}
                        div = meta.get("division", "GENERAL")
                        ts = meta.get("timestamp", "")
                        tags = meta.get("tags", "")
                        title = safe_name(content.split("]")[0].lstrip("[") if content.startswith("[")
                                          else content[:50])
                        f = snap / f"{safe_name(rid or title, 40)}.md"
                        f.write_text(
                            f"---\ntopic: {title}\ndivision: {div}\n"
                            f"source_id: {rid}\ntimestamp: {ts}\ntags: {tags}\n---\n"
                            f"{content}\n", encoding="utf-8")
                        written += 1
                except Exception as e:
                    print(f"  [warn] '{q}' 질의 실패: {type(e).__name__}: {e}")
            print(f"  [OK] {written}개 기억을 {snap} 에 노트로 저장")

    # ── 마무리 안내 ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("완료. 옵시디언 앱에서:")
    print("  '다른 보관소 열기(Open folder as vault)' →")
    print(f"  {vault}")
    print("선택하면 위키 볼트가 열립니다.")
    if not args.seed:
        print("\nTIP: 지금 RAG 기억으로 채워 보려면 --seed 붙여 다시 실행:")
        print(f"  py setup_obsidian.py --root {args.root} --seed")
    print("=" * 60)


if __name__ == "__main__":
    main()
