# Mokai Brain Kit — 스킬 번들 설치 가이드

## 포함 스킬 6종

| 스킬 | 역할 |
|------|------|
| **graphify** | 코드/메모리 지식 그래프 생성 — `/graphify` 명령으로 코드베이스를 그래프화, grep 대신 구조 검색 |
| **karpathy-guidelines** | Karpathy 스타일 코딩 원칙 적용 — 간결하고 검증 가능한 코드 작성 가이드 |
| **para-memory-files** | PARA 방식 메모리 파일 관리 — Projects/Areas/Resources/Archives 구조로 장기기억 정리 |
| **youtube-summary** | YouTube 영상 요약 — yt-dlp로 자막 추출 후 Claude가 요약 (URL 한 줄이면 동작) |
| **superpowers** | 고급 개발 워크플로 (TDD, 디버깅, 코드리뷰, 플래닝 등) — plugins.zip에 포함 |
| **serena** | LSP 기반 코드 분석 MCP — 심볼 단위 검색·편집, 토큰 절약 — plugins.zip에 포함 |

---

## 설치 필요 여부 구분

| 스킬 | SKILL.md 배치만으로 동작? | 추가 도구 설치 필요 |
|------|--------------------------|---------------------|
| graphify | 부분 (명령어 인식은 됨) | **`uv tool install graphifyy`** + PATH 등록 필요 |
| karpathy-guidelines | **예** | 없음 |
| para-memory-files | **예** | 없음 |
| youtube-summary | 부분 (자막 없으면 동작 안 함) | **`pip install yt-dlp`** 필요 |
| superpowers | **예** (plugins 설치 후) | 없음 |
| serena | 아니오 — MCP 등록 필수 | **`pip install serena-agent`** + MCP 등록 |

---

## 설치 방법

### 1단계 — 스크립트 실행

```bash
python install_skills.py
# 다른 Claude 홈 경로면:
python install_skills.py --claude-home "C:\Users\YourName\.claude"
```

설치 스크립트가 자동으로:
- `skills/` 아래 4개 폴더를 `~/.claude/skills/`에 복사 (기존 스킬은 건드리지 않음)
- `plugins.zip`을 `~/.claude/`에 압축 해제 (superpowers + serena 병합)
- graphify / yt-dlp / serena-agent pip/uv 설치 시도 (실패해도 중단 안 함)

### 2단계 — Claude Code 재시작

스킬은 Claude Code 시작 시 로드됩니다. **반드시 재시작** 후에 적용됩니다.

---

## Serena MCP 등록 안내

serena는 MCP 서버로 동작하므로 pip 설치 후 별도 등록이 필요합니다.

**방법 A — marketplace 자동 등록 (plugins.zip 설치 시)**
plugins.zip의 serena 플러그인이 marketplace에 등록되어 있으면 Claude Code가 자동 인식합니다.
Claude Code 재시작 후 `/mcp` 명령으로 serena가 보이면 완료.

**방법 B — CLI 수동 등록**
```bash
claude mcp add serena-agent
```

**방법 C — ~/.claude.json 직접 편집**
```json
{
  "mcpServers": {
    "serena": {
      "command": "python",
      "args": ["-m", "serena_agent"],
      "type": "stdio"
    }
  }
}
```

---

## graphify PATH 등록

`uv tool install graphifyy` 성공 후 PATH에 uv tools bin 경로를 추가해야 합니다.

**Windows**
```powershell
# uv tools 기본 bin 경로 확인
uv tool dir
# 출력 경로를 시스템 PATH에 추가 (사용자 환경변수)
```

**Claude Code에서 사용**
```
/graphify .          # 현재 디렉토리 코드 그래프 생성
graphify query "..."  # 그래프 검색
```

---

## 함정 메모

| 상황 | 해결 |
|------|------|
| `uv` 설치 후 Python 없다고 오류 | `uv python install 3.13` 선행 필요 |
| Windows에서 claude CLI `--` 인자가 소비됨 | `cmd /c claude ...` 로 우회 |
| yt-dlp YouTube 자막 연속 호출 시 429 | 쿠키 필요: 브라우저 종료 후 cookies.txt 추출 |
| serena MCP 연결 안 됨 | Claude Code 재시작 후 `/mcp status` 확인 |

---

*Mokai Brain Kit 3.5.0 — 스킬 번들*
