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
' ASCII-only comments (wscript parses this file as ANSI).
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\\leaf\\memory"
WshShell.Run "cmd /c python -m brain_share.sync_agent --config C:/leaf/memory/brain_share_config.json --node leaf-원하는이름 --intake http://{main_host}:9212/intake > C:\\leaf\\memory\\sync_boot.log 2>&1", 0, False
```

- ★**`cmd /c ... > 로그 2>&1` 래핑은 필수**입니다. `WshShell.Run "python ...", 0, False`처럼 맨몸으로 부르면 stdout 핸들이 없어 **로그 한 줄 없이 조용히 기동 실패**합니다. 게다가 작업 스케줄러는 wscript 종료코드만 보므로 `LastResult=0`(성공)으로 기록해 실패를 은폐합니다. 실측 4건.
- ★**`pythonw`가 아니라 `python`**을 씁니다. pythonw는 stdout/stderr가 없어 리다이렉트해도 빈 로그만 남습니다(= 실패 원인 추적 불가).
- 기동 확인은 `sync_boot.log`로 — 파일이 안 생겼으면 VBS가 아예 안 돈 것이고, 비어 있으면 정상 상주 중입니다.
- `CurrentDirectory`는 반드시 메모리 루트(그 안에 `brain_share/` 폴더가 있는 곳)로 — `-m` 임포트가 여기서 됨.
- `--node`/`--intake`는 3단계 환경변수(`AGENT_NAME`/`BRAIN_INTAKE_URL`)가 있으면 생략 가능.
- 동작: `C:/leaf/memory/outbox/*.json` 에 떨군 파일을 180초 주기로 큐에 담아 메인에 업로드, 처리분은 `outbox/sent/` 로 이동. 수동 1회 실행은 `--once`.

## 5. 업로드 아이템 스키마 (중요 — 어기면 전량 거부)

`outbox/*.json` 은 아이템 dict 1개 또는 dict 배열. 필드 규칙:

```json
{{
  "content": "본문 (필수, 비어있으면 거부)",
  "collection": "knowledge",
  "metadata": {{"division": "SYSTEM", "tags": ["..."]}},
  "topic": "선택"
}}
```

- **`collection` 필수**: 메인 intake 필터가 allowed_collections(`wiki`/`knowledge`/`decisions`/`conversations`/`tasks`)와 대조 — 없거나 다른 값이면 **"sensitive"로 거부**됨. sync_agent CLI는 누락 시 `knowledge`를 자동 주입.
- **`division`은 `metadata.division`에만**: top-level `division`은 무시됨. 메인 blocked_divisions에 걸리면 거부(정상 동작).
- `content`가 blocked_keyword_patterns(예: api_key, secret)에 걸려도 거부됨.

---

## 메인 운영자 메모

- 새 하위 추가 = 위 1~5단계 복붙 (5는 스키마 숙지).
- read_key는 **비밀** (LAN 외부 노출 금지). 외부 노출 시 즉시 메인 brain_share_config.json 의 read_key를 새 값으로 교체하고 모든 하위 재등록.
- 메인 IP/도메인 변경 시 이 파일의 `{main_host}` 자리만 일괄 수정 + 모든 하위 재등록.
- 메인 서버 가동:
  - 게이트웨이 (읽기 :9211) — `python -m brain_share.gateway_mcp --config <cfg>`
  - intake (쓰기 :9212) — `python -m brain_share.intake_server --config <cfg> --incoming <ROOT>/incoming`
  - 정본화 데몬 — `python -m brain_share.synth_daemon --config <cfg> --incoming <ROOT>/incoming --vault <볼트> --interval 1800`
  - 대시보드 (관측 :9213) — `python brain_dashboard.py --root <ROOT>`
- ★메인 서버들을 VBS로 부팅 자동시작 걸 때도 위 4단계와 **똑같이 `cmd /c ... > 로그 2>&1`로 감쌉니다.** 안 감싸면 조용히 안 뜹니다.
"""


def emit_leaf_registration(root, read_key: str, main_host: str = None,
                           version: str = "3.4.2",
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
