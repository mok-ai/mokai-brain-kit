"""
setup_identity.py — 에이전트 정체성 설정 (이름 + CLAUDE.md)
멱등 동작: 기존 이름/CLAUDE.md 있으면 절대 덮어쓰지 않음.
stdlib only (no third-party dependencies).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

print("Mokai Brain Kit 3.2.1")

# ── 기본값 ─────────────────────────────────────────────────────────────────
DEFAULT_ROOT = Path.home() / ".claude"
TEMPLATE_NAME = "CLAUDE_TEMPLATE.md"
GENERIC_SKIP_NAMES = {"kim", "agent", "assistant", "claude", ""}


def _find_template(root: Path) -> Path | None:
    """CLAUDE_TEMPLATE.md를 스크립트 위치 → root 순으로 탐색."""
    candidates = [
        Path(__file__).parent / TEMPLATE_NAME,
        root / TEMPLATE_NAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _already_has_identity(root: Path) -> tuple[bool, str]:
    """
    기존 정체성 여부 판단.
    True 반환 시: (True, 감지된 근거 설명)
    """
    # 1) 환경변수 AGENT_NAME 이 의미 있는 값이면 정체성 있음
    env_name = os.environ.get("AGENT_NAME", "").strip().lower()
    if env_name and env_name not in GENERIC_SKIP_NAMES:
        return True, f"환경변수 AGENT_NAME='{os.environ['AGENT_NAME']}' 이미 설정됨"

    # 2) memory_config.py 가 있고 agent_ 이 아닌 다른 접두어를 쓰면 정체성 있음
    mc = root / "memory_config.py"
    if mc.exists():
        try:
            text = mc.read_text(encoding="utf-8", errors="replace")
            # COLLECTIONS dict 안에 'agent_'이 없지만 '_' 를 포함하는 컬렉션명이 있으면 커스텀
            import re
            names = re.findall(r'"(\w+_\w+)"', text)
            non_kim = [n for n in names if not n.startswith("agent_") and "_" in n]
            if non_kim:
                return True, f"memory_config.py에 커스텀 컬렉션 감지: {non_kim[:3]}"
        except Exception:
            pass

    # 3) CLAUDE.md 가 이미 있으면 정체성 있음
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        return True, f"CLAUDE.md 이미 존재: {claude_md}"

    return False, ""


def _set_agent_name(name: str) -> bool:
    """
    사용자 환경변수 AGENT_NAME 영구 설정 시도 (setx).
    성공 여부 반환.
    """
    try:
        result = subprocess.run(
            ["setx", "AGENT_NAME", name],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def _render_template(template_text: str, name: str, role: str) -> str:
    return (
        template_text
        .replace("{{AGENT_NAME}}", name)
        .replace("{{ROLE_DESC}}", role)
    )


def main():
    parser = argparse.ArgumentParser(
        description="에이전트 정체성 설정 (이름 + CLAUDE.md) — 멱등 동작"
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help=f"에이전트 홈 디렉토리 (기본: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--name",
        default="",
        help="에이전트 이름 (예: myagent, assistant). 없으면 이름 설정 건너뜀.",
    )
    parser.add_argument(
        "--role",
        default="회사",
        help="역할 설명 (기본: '회사'). CLAUDE.md {{ROLE_DESC}} 자리에 삽입.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    name_given = args.name.strip()
    role = args.role.strip() or "회사"

    print("=" * 60)
    print("  setup_identity.py — 에이전트 정체성 설정")
    print(f"  root : {root}")
    print(f"  name : {name_given or '(미지정)'}")
    print(f"  role : {role}")
    print("=" * 60)

    # ── 1. 이름(AGENT_NAME) 멱등 설정 ─────────────────────────────────────
    print("\n[1/2] 이름(AGENT_NAME) 설정")

    has_id, reason = _already_has_identity(root)
    name_action = ""

    if has_id:
        print(f"  → 이미 정체성 있음 ({reason})")
        print("  → 이름 설정 건너뜀 (기존 정체성 보존)")
        name_action = "SKIP (기존 정체성 감지)"
        # CLAUDE.md 생성에 쓸 이름은 환경변수 또는 기존 값 사용
        effective_name = os.environ.get("AGENT_NAME", "").strip() or name_given or "agent"
    elif not name_given:
        print("  → --name 이 지정되지 않았습니다.")
        print("  → 이름을 --name 으로 지정하세요. 예:")
        print("       python setup_identity.py --name myagent --role 회사이름")
        name_action = "SKIP (--name 미지정)"
        effective_name = "agent"
    else:
        effective_name = name_given
        print(f"  → AGENT_NAME='{effective_name}' 영구 설정 시도 중...")
        ok = _set_agent_name(effective_name)
        if ok:
            print(f"  → setx 성공: AGENT_NAME={effective_name}")
            print("     (이 터미널 세션에서는 아직 미반영; 새 터미널/재로그인 후 적용)")
            name_action = f"SET: AGENT_NAME={effective_name}"
        else:
            print(f"  → setx 실패 또는 미지원. 아래 명령을 직접 실행하세요:")
            print(f"       setx AGENT_NAME {effective_name}")
            name_action = f"MANUAL NEEDED: setx AGENT_NAME {effective_name}"

    # ── 2. CLAUDE.md 멱등 생성 ─────────────────────────────────────────────
    print("\n[2/2] CLAUDE.md 생성")
    claude_md = root / "CLAUDE.md"

    if claude_md.exists():
        print(f"  → 기존 CLAUDE.md 보존, 덮어쓰지 않음: {claude_md}")
        md_action = "SKIP (기존 파일 보존)"
    else:
        template_path = _find_template(root)
        if template_path is None:
            print(f"  → CLAUDE_TEMPLATE.md 를 찾을 수 없습니다.")
            print(f"     탐색 위치: {Path(__file__).parent} , {root}")
            print("     CLAUDE_TEMPLATE.md 를 같은 폴더에 두고 다시 실행하세요.")
            md_action = "FAIL (템플릿 없음)"
        else:
            template_text = template_path.read_text(encoding="utf-8")
            rendered = _render_template(template_text, effective_name, role)
            claude_md.write_text(rendered, encoding="utf-8")
            print(f"  → CLAUDE.md 생성 완료: {claude_md}")
            md_action = f"CREATED: {claude_md}"

    # ── 3. 최종 요약 ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  [완료 요약]")
    print(f"  이름 설정   : {name_action}")
    print(f"  CLAUDE.md   : {md_action}")
    print()
    print("  다음 안내:")
    print("  • Claude Code를 재시작해야 CLAUDE.md 가 적용됩니다.")
    if "SET:" in name_action:
        print("  • AGENT_NAME 은 새 터미널/재로그인 후 환경변수에 반영됩니다.")
    if "SKIP" in name_action and not has_id:
        print("  • 이름 변경: --name 을 다시 지정해서 실행하세요.")
    if "SKIP" in name_action and has_id:
        print("  • 정체성을 변경하려면 기존 CLAUDE.md / AGENT_NAME 을 직접 수정하세요.")
    print("=" * 60)


if __name__ == "__main__":
    main()
