"""Generate LEAF_REGISTRATION.md — copy-paste commands for adding a sub-PC.

The file is written once at main-install time and read back later when the
operator (or main brain's secretary AI) is asked "how do I register a new
leaf?".  Idempotent: regenerating with new args is a no-op if the file
already exists, so the read_key minted at first install is never rotated
silently.
"""
import datetime
from pathlib import Path

PLACEHOLDER_HOST = "<MAIN_HOST_IP_OR_DOMAIN>"


def render_leaf_registration(read_key: str, main_host: str, version: str,
                             today: str) -> str:
    """Return the markdown body. Pure — no IO."""
    key_prefix = (read_key or "")[:8]
    return f"""# 하위 PC 등록 명령 — Mokai Brain Kit {version}

이 파일은 메인 브레인 설치 시 자동 생성됩니다. 새 하위 PC를 통합 브레인에 합류시킬 때 아래 명령을 그대로 복붙하세요.

- 발급일: {today}
- 메인 호스트: `{main_host}`  ← 플레이스홀더면 실제 LAN IP / Cloudflare 도메인으로 교체
- read_key SHA prefix: `{key_prefix}…`

---

## 1. 하위 PC에 패키지 설치

```
python install.py --root C:/leaf/memory
```

설치 후 생성된 `C:/leaf/memory/brain_share_config.json` 의 `"read_key"` 를 아래 값으로 교체 (메인 키와 일치해야 인증됨):

```
{read_key}
```

## 2. 읽기(MCP) 등록 — 하위 Claude Code 터미널에서

```
claude mcp add --transport http company-brain http://{main_host}:9211/mcp --header "X-Brain-Key: {read_key}"
```

이걸로 하위 Claude가 `search_company_brain` · `get_company_context` · `related_in_brain` · `graph_neighbors` 4툴을 사용. "통합 브레인에서 ○○ 찾아봐" 한 마디로 호출.

## 3. 쓰기(sync_agent) 환경변수 — 하위 PC PowerShell에서

```
setx BRAIN_INTAKE_URL "http://{main_host}:9212/intake"
setx BRAIN_READ_KEY   "{read_key}"
setx AGENT_NAME       "leaf-원하는이름"
```

## 4. sync_agent 부팅 등록 (자동 업로드, 콘솔 숨김)

`C:/leaf/start_sync.vbs` 저장 후 시작프로그램(`shell:startup`)에 둠:

```vbscript
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw -m brain_share.sync_agent --config C:/leaf/memory/brain_share_config.json --node leaf-원하는이름 --intake http://{main_host}:9212/intake", 0, False
```

(또는 동등한 Python 한 줄을 시작프로그램에 등록 — 환경변수 사용 가능)

---

## 메인 운영자 메모

- 새 하위 추가 = 위 1~4단계 복붙.
- read_key는 **비밀** (LAN 외부 노출 금지). 외부 노출 시 즉시 메인 brain_share_config.json 의 read_key를 새 값으로 교체하고 모든 하위 재등록.
- 메인 IP/도메인 변경 시 이 파일의 `{main_host}` 자리만 일괄 수정 + 모든 하위 재등록.
- 메인 서버 가동:
  - 게이트웨이 (읽기 :9211) — `python -m brain_share.gateway_mcp --config <cfg>`
  - intake (쓰기 :9212) — `python -m brain_share.intake_server --config <cfg> --incoming <ROOT>/incoming`
  - 정본화 데몬 — `python -c "from brain_share.synth_daemon import run_daemon; ..."`
"""


def emit_leaf_registration(root, read_key: str, main_host: str = None,
                           version: str = "3.1.1",
                           today: str = None) -> Path:
    """Write LEAF_REGISTRATION.md under root, idempotent.

    Returns the path. If the file already exists, returns it unchanged —
    callers must not overwrite (would rotate a documented read_key silently).
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    reg_md = root / "LEAF_REGISTRATION.md"
    if reg_md.exists():
        return reg_md
    host = main_host or PLACEHOLDER_HOST
    if today is None:
        today = datetime.date.today().isoformat()
    body = render_leaf_registration(read_key=read_key, main_host=host,
                                    version=version, today=today)
    reg_md.write_text(body, encoding="utf-8")
    return reg_md
