# Mokai Brain Kit — 변경 이력 (CHANGELOG)

모든 주요 변경 사항을 이 파일에 기록합니다. [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 형식 준수.

---

## [3.5.0] - 2026-07-27

### 🔒 보안 — 공개 배포본에 빌드 머신의 개인 계정 경로 포함 (v3.0.1~v3.4.2)
- `skills_bundle/plugins.zip` 안의 `installed_plugins.json` · `known_marketplaces.json`이 빌드 머신의 절대경로(`C:\Users\<계정>\.claude\plugins\...`)를 그대로 담고 있었다. **11개 공개 릴리스 자산 전부**에 포함. 3.0.0의 "내부 식별자 전량 제거" 전수 검사가 **zip 안의 zip까지는 보지 못했다.**
- 부수 피해: 그 경로는 다른 머신에서 유효하지 않으므로 플러그인 등록이 애초에 어긋나 있었다.
- **조치**: ①번들에서 두 파일 제외 — 이제 `plugins.zip`은 캐시 트리만 담는다. ②`install_skills.py`가 설치 시점에 **로컬 경로로 레지스트리를 재생성**(`plan_registry`/`plan_marketplaces`, 사용자가 이미 설치한 플러그인 항목은 보존하는 additive 병합). ③GitHub Release 자산 11개 및 배포 서버의 구버전 zip 전량 삭제.
- **회귀 방지**: 산출물 자체를 검사하는 테스트 추가 — 배포될 `plugins.zip`에 `installed_plugins.json`·개인경로·`installLocation`이 없어야 통과.
- ★교훈: **중첩 아카이브는 grep의 사각지대다.** 배포 전 검사는 zip 안의 zip까지 풀어서 본다.

### 추가 — 자가복구 워치독 (`brain_share/watchdog.py` + `brain_watchdog.py`)
등록돼 있다고 뜨는 게 아니다. 2026-07-27 실측: autostart 4종이 등록·활성·대화형 로그온 정상인데도 재부팅 후 **하나도 뜨지 않았고, 로그조차 없었다.**
- 포트 프로브 → 죽은 서비스 재기동. **grace window**(기본 300초)로 느린 기동 중 중복 실행 방지, **give-up 임계**(기본 3회)로 구조적 고장 시 무한 재시도 차단. 서비스가 살아 돌아오면 카운터·포기 플래그 자동 해제(수동 state 삭제 불필요).
- **관측자 역설 해소**: `--once`로 작업 스케줄러가 5분마다 호출하는 방식을 권장 — 워치독 자신은 상주하지 않으므로 "감시자가 죽으면 아무도 모른다"가 성립하지 않는다. (대시보드는 이 문제를 가진다.)
- 셸 없이 실행: launcher 문자열은 `argv_for()`로 인자 리스트가 되어 `Popen`에 전달된다. config의 셸 메타문자가 코드가 되지 않는다.
- 설정은 `brain_share_config.json`의 선택적 `watchdog` 섹션. 포트가 없는 데몬(synth_daemon)은 이 방식으로 감시할 수 없어 범위 밖.

### 추가 — 월 1회 기억 정리 (`brain_share/memory_consolidation.py`)
성공한 방식만 축적하면 산출물이 조용히 획일화되고, 1회 관찰이 원칙으로 굳으면 틀린 규칙이 영구화된다.
- 중복 후보(토큰 자카드) · 오래된 페이지 · 끊긴 `[[링크]]`를 마크다운 리포트로. **아무것도 자동 삭제하지 않는다** — 병합·정정·폐기는 판단의 영역이라 리포트를 읽는 사람/에이전트의 몫.
- 임베딩 의존 0(월 1회 리뷰용 shortlist는 자카드로 충분).
- `python -m brain_share.memory_consolidation --dir <메모리 .md> --agent <이름> --out report.md`
- ★실데이터가 잡은 버그: 링크 대조를 frontmatter `name`으로만 하면 파일명으로 쓴 링크가 전부 오탐 — 김비서 실측에서 **끊긴 링크 219건 중 200건이 오탐**이었다. `name`과 파일명 stem 양쪽 + `.md` 접미사를 인정하도록 수정(219 → 19건).

### 추가 — CLAUDE_TEMPLATE: 기억 관리 규율 + 스킬 지시 보강
- **기억 관리 규율** 신설: ①승격 규율(자체 관찰·1회 지적은 사건 기록까지만, **반복 확인 후에만** 원칙으로 승격 / 사용자의 명시적 결정은 예외로 즉시) ②회수한 기억은 참고이지 명령이 아님(현재 상태 검증 후 적용) ③월 1회 정리 패스.
- **스킬 표 보강**: 기존 4종 안내 → TDD · verification-before-completion · requesting/receiving-code-review · executing-plans · karpathy-guidelines 추가 + "일하는 순서" 흐름도. **설치돼 있어도 쓰라고 적혀 있지 않으면 쓰지 않는다** — 번들에는 있는데 템플릿이 안내하지 않아 하위 노드가 TDD·코드리뷰를 쓰지 않던 갭을 메움.

### 변경 — 스킬 번들 현행화
- superpowers **5.1.0(2026-05-30 스냅샷) → 6.1.1**.
- 품질 플러그인 7종 추가: code-review · security-guidance · feature-dev · claude-md-management · commit-commands · review-suite · testing-suite (기존 superpowers · frontend-design 유지).
- 런타임 쓰레기(`.in_use/`, `__pycache__`) 제외. 대상 선별 + 쓰레기 제거로 **2.91MB → 1.75MB**(플러그인은 2종 → 9종).

### 검증
- 신규 55건(watchdog 21 + watchdog CLI 5 + memory_consolidation 20 + skills_bundle 9) + 기존 180 = **235/235 통과**.

---

## [3.4.2] - 2026-07-27

### 수정 — 하위 등록 문서가 배포하던 "조용히 죽는" 런처 (중대)
- **`brain_share/leaf_registration.py`**: `LEAF_REGISTRATION.md`가 운영자에게 발급하는 4단계 sync_agent 부팅 등록 VBS가 `WshShell.Run "pythonw -m brain_share.sync_agent ...", 0, False` — **맨몸 Run + pythonw** 조합이었다. 3.4.1이 바로 이 함정(`cmd /c ... > log 2>&1` 미래핑 시 stdout 핸들이 없어 로그 한 줄 없이 기동 실패)을 CHANGELOG "참고" 항목으로 기록해 놓고, **정작 제품이 발급하는 템플릿은 고치지 않았다.** 문서대로 복붙한 모든 신규 leaf는 sync_agent가 뜨지 않고, 실패 흔적조차 남지 않는다.
  - `cmd /c python -m ... > <ROOT>/sync_boot.log 2>&1` 래핑으로 교체.
  - `pythonw` → `python`. pythonw는 stdout/stderr가 없어 래핑해도 빈 로그만 남는다(원인 추적 불가).
  - 래핑이 왜 필수인지 + `sync_boot.log`로 기동을 판정하는 법을 문서 본문에 명시.
- **부수 수정**: `emit_leaf_registration`의 `version` 기본값이 `3.2.2`로 낡아 있던 것을 현행화. 메인 운영자 메모의 정본화 데몬 안내를 3.3.0에서 신설된 CLI(`python -m brain_share.synth_daemon --config ... --interval`)로 갱신하고, 대시보드(:9213) 기동 명령과 "메인 서버 VBS도 똑같이 래핑하라"는 경고를 추가.

### 검증
- 신규 테스트 2건 — 템플릿의 모든 `.Run` 명령이 `cmd /c` + 로그 리다이렉트 + `2>&1`을 갖출 것, `pythonw`를 쓰지 않을 것. 수정 전 상태에서 두 건 모두 FAIL로 결함 재현 후 수정(RED→GREEN).
- 기존 178 + 신규 2 = **180/180 통과**.

### 참고 — 운영 교훈 (김비서 본체 실측)
- 3.4.1이 함정을 **문서에만** 적고 코드에 반영하지 않아 5일간 잠복했다. 함정을 발견하면 CHANGELOG 기록과 **제품 템플릿·런처 생성 코드 수정을 같은 커밋에서** 끝낸다.
- 자동시작을 `HKCU\...\Run`에 걸어 둔 데몬 4종이 재부팅 후 하나도 뜨지 않는 사례가 실측됐다(레지스트리 등록·StartupApproved 플래그 모두 정상, 대화형 로그온도 존재). Run 키는 실패해도 흔적이 없으므로, 상시 데몬은 **작업 스케줄러 로그온 트리거**(지연 1분)로 등록하는 편이 안전하다.

---

## [3.4.1] - 2026-07-22

### 수정 — 관계그래프 영구 정지 (중대)
- **`brain_share/selfsynth_batch.py`**: 자가 정본화 배치가 관계그래프에 넘기는 `unit_id`가 토픽 slug(`<prefix>_00`)였다. slug는 배치마다 **재사용되는 고정 이름**이라 `graph_batch.is_processed()`가 2회차부터 전 토픽을 skip → **관계그래프가 첫 스냅샷에서 영구 정지**. 원본 기억이 계속 늘어도 그래프는 자라지 않는다. `unit_id`를 내용(엔티티) 해시 기반 `<slug>@<ent_sig>`로 변경 — 내용이 바뀌면 재집계, 동일하면 skip(멱등 보존).
- 영향: `selfsynth_batch`를 **2회 이상 실행하는 모든 노드**. "관계는 살아 진화한다"는 핵심 가치가 구조적으로 무력화돼 있었다.

### 검증 (김비서 본체 실측, kim_knowledge 9,875건)
- 수정 전: `processed 0 / skipped 8` → 노드 48 · 엣지 473 (2026-06-26 이후 정지)
- 수정 후: `processed 8 / skipped 0` → **노드 158 · 엣지 1,375** (3.3배 / 2.9배)
- 신규 테스트 2건(내용 변경 시 재집계 / 동일 재실행 시 멱등 유지) + 기존 176 = **178/178 통과**

### 참고 — 운영 함정 (동일 원인 4건 실측)
- VBS 런처에서 `sh.Run "python ...", 0, False`는 stdout 핸들이 없어 **조용히 기동 실패**한다(로그조차 안 남음). 스케줄러는 wscript 종료코드만 보므로 `LastResult=0`(성공)으로 기록되어 실패가 은폐된다. 반드시 `cmd /c ... > <boot>.log 2>&1`로 감싼다.

---

## [3.4.0] - 2026-07-20

### 추가 — B1 통합 대시보드
- **`brain_share/dashboard_scanner.py`**: 순수 read-only 스캐너 6종 — `scan_incoming` (노드별 업로드 카운트/사이즈/마지막 업로드 시각), `scan_backups` (매일 스냅샷 목록 + chroma sha prefix), `scan_synth_watermark` (정본화된 토픽 수), `scan_graph` (관계그래프 노드/엣지/top-degree), `scan_servers` (RAG/게이트웨이/intake 포트 헬스), `collect_all` (전체 aggregate). 모든 함수 에러 시 빈 구조 반환 — 하나 실패해도 대시보드 나머지 표시. `scan_incoming`은 라이브 멀티라이터 incoming의 glob→stat TOCTOU 레이스를 파일별 가드, `scan_backups`는 valid-JSON-but-wrong-shape manifest를 스킵(크래시 대신).
- **`brain_dashboard.py`** (top-level): stdlib `http.server` 기반 로컬 대시보드. `GET /api/status` → aggregate JSON, `GET /` → 단일 HTML 페이지 (vanilla JS, 30초 auto-refresh, 다크 테마, 카드 5개: Servers/Incoming/Backups/Synth/Graph). 스캐너 문자열은 `esc()`로 XSS 이스케이프. Flask 등 외부 의존 0. 기본 바인딩 `127.0.0.1:9213`, LAN 노출은 `BRAIN_DASHBOARD_HOST=0.0.0.0` env opt-in (무인증이므로 필요 시에만).

### 검증
- 신규 21건(scanner 14 + 방어 보강 2 + HTTP 5) + 기존 155 = **176/176 통과**.
- 스캐너 모든 소스 미존재/malformed 시나리오 커버(파일시스템/SQLite/포트 + stat 레이스 + 깨진 manifest).
- HTTP handler는 in-process request test로 socket 없이 검증.

### 사용
```bash
python brain_dashboard.py --root C:/brainkit/memory
# 브라우저에서 http://127.0.0.1:9213 → 실시간 상태

# LAN 노출 (필요 시)
BRAIN_DASHBOARD_HOST=0.0.0.0 python brain_dashboard.py --root ...
```

---

## [3.3.0] - 2026-07-19

### 추가 — A 묶음 (wiki 검색 노출 + 백업/롤백 + 상주 정본화)
- **`brain_share/wiki_search.py`** + **`memory_mcp.recall_memory(wiki_first=True)`**: RAG API 리랭커가 정본 위키를 걸러내는 문제를 우회. chroma_db 직접 쿼리(lazy embedder 로드)로 `<agent>_wiki` 컬렉션 결과를 먼저 뽑고 RAG API 결과와 id 기준 dedupe/merge. RAG나 embedder 로드가 실패해도 조용히 빈 리스트 반환 → 기존 사용자 무영향.
- **`backup.py`** + **`restore.py`** (top-level): 매일 세대 스냅샷(`chroma_db.zip` / `obsidian.zip` / `brain_share_config.json` / `memory_config.py` / `LEAF_REGISTRATION.md` + `manifest.json`). 기본 7일 보존, cutoff = `today - (keep_days-1)`. PC가 며칠 꺼져 있어도 오래된 백업을 시간축으로 정확히 정리. `restore.py`는 dry-run 기본, `--yes` 명시해야 실제 원복. `_zip_dir`는 sorted rglob으로 SHA 결정성 보장.
- **`autostart.py`** (top-level) + **`brain_share/synth_daemon.py`** CLI 엔트리: HKCU Run 키 등록/해제 helper(`BrainKit*` 접두어로 자체 항목만 열람) + `python -m brain_share.synth_daemon --config <cfg> --incoming <dir> --vault <dir> --interval 1800` 상주 데몬. 30분 주기(기본)로 incoming 감지 → 증분 정본화. winreg는 lazy import (non-Windows 안전).

### 검증
- 신규 3파일 단위테스트 20건(wiki 6 + backup/restore 8 + autostart 6, CLI 1) + 기존 134 = **155/155 통과**.
- 무거운 의존(chromadb / sentence-transformers / winreg) 전부 lazy import + 주입형 → GPU/윈도 API 없이 결정적 단위테스트.
- 리뷰 라운드: Task 2에서 Important 2건 발견(prune 알고리즘 브리프 이탈 · zip 결정성 없음) → fix 라운드로 date-cutoff 복원 + `sorted(rglob)` 적용. 재리뷰 클린.

### 사용
```bash
# 매일 세대 백업 (작업 스케줄러 03:00 등록)
python backup.py --root C:/brainkit/memory --keep-days 7

# 상주 정본화 데몬 (백그라운드)
python -m brain_share.synth_daemon --config brain_share_config.json \
  --incoming C:/brainkit/memory/incoming --vault C:/brainkit/obsidian

# 자동시작 등록/해제
python autostart.py register BrainKitSynthDaemon "wscript C:/brainkit/start_synth.vbs"
python autostart.py list
```

---

## [3.2.2] - 2026-07-06

첫 라이브 MCP 클라이언트 접속(leaf 합류)에서 발견된 게이트웨이 인증 치명 버그 수정 (PATCH — 기능 추가 없음, 툴 API 무변경).

### 수정
- **`gateway_mcp.py` — MCP 툴 4종 Context 미주입으로 인증 상시 실패**: `search_company_brain` / `get_company_context` / `related_in_brain` / `graph_neighbors_tool`의 `ctx=None` 파라미터에 `Context` 타입 어노테이션이 없어 FastMCP가 요청 컨텍스트를 주입하지 않음 → `_auth()`가 `X-Brain-Key` 헤더를 읽지 못해 항상 인증 실패 → 모든 실제 MCP 클라이언트에 조용히 빈 결과만 반환되던 버그. `from mcp.server.fastmcp import FastMCP, Context` 임포트 + 4개 시그니처를 `ctx: Context = None`으로 수정. (기존 유닛테스트는 가짜 ctx를 함수에 직접 전달해 통과했기 때문에 라이브 주입 경로가 미커버였음.)

### 검증
- 신규 4 단위테스트 `test_gateway_mcp.py`: FastMCP 등록 메타데이터로 4개 툴 전부 `Tool.context_kwarg == "ctx"` 확인(어노테이션 누락 시 즉시 FAIL하는 회귀 방어) + 컨텍스트 부재 fail-closed + 정상 키 서빙 + 오류 키 거부. 버그 재현 상태에서 실제 FAIL함을 역검증.
- 130+4 = **134/134 통과** (패키지·github src 양쪽 레이아웃).
- 메인 HUB 라이브 게이트웨이(:9211)에 선적용 — 실제 leaf MCP 클라이언트에서 search 5건 정상 반환 실증.

---

## [3.2.1] - 2026-07-06

첫 실가동 leaf(OH PC) 설치에서 발견된 버그 3건 수정 (PATCH — 기능 추가 없음, 기존 API 무변경).

### 수정
- **`healthcheck.py` — 콘솔 cp949 크래시**: Windows 콘솔(cp949)에서 em-dash(—) 등 비ASCII print 시 UnicodeEncodeError로 진단 자체가 중단. `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` 강제 (install.py v3.0.1과 동일 패턴 — v3.2.0 외부 기여 파일에 미적용이었음).
- **`sync_agent.py` — CLI 진입점 신설 (LEAF_REGISTRATION 4단계 명령 동작 불가 해소)**: 기존 문서의 `pythonw -m brain_share.sync_agent --config … --node … --intake …`가 `__main__`/argparse 부재로 동작하지 않던 문서 버그. outbox 디렉토리 방식 CLI 추가 — `<ROOT>/outbox/*.json` 드롭 → SQLite 큐 → 메인 intake 업로드, 처리분 `outbox/sent/` 이동, `collection` 누락 시 `knowledge` 자동 주입, malformed 파일은 보존·재시도. `--once`(1회 실행), `--outbox`/`--queue`/`--collection`/`--period` 옵션, `--node`/`--intake`는 `AGENT_NAME`/`BRAIN_INTAKE_URL` env 폴백. stdlib 전용 유지(무거운 의존 0).
- **`leaf_registration.py` — 4단계 VBS 수정 + 업로드 스키마 문서화**: VBS에 `WshShell.CurrentDirectory = 메모리루트` 추가(`-m` 임포트 필수 조건), 신규 "## 5. 업로드 아이템 스키마" 섹션 — intake 필터가 item의 `collection`을 allowed_collections와 대조하므로 **`collection` 없는 아이템은 전부 "sensitive" 거부**, `division`은 top-level이 아닌 **`metadata.division`만 인정**함을 명시. README 6장에도 동일 스키마 문서 추가.

### 검증
- 신규 4 단위테스트(outbox collection 주입·sent 이동 / malformed 보존 / CLI `--once` 종단 / 필수 인자 검증). 126+4 = **130/130 통과**.
- healthcheck.py는 `PYTHONIOENCODING=cp949` 강제 상태에서 전 항목 출력 완주 확인.

---

## [3.2.0] - 2026-07-03

### 추가 — 3가지 설치 후 유틸리티 (외부 기여)
GitHub PR #1 병합. 다른 에이전트가 자체 설치 과정에서 만든 실용 도구 3종을 브레인 키트 표준으로 편입.

- **`healthcheck.py`** — 로컬 장기기억 종합 진단기(읽기 전용, 무손상). 6영역 점검: (1) 메모리 루트 / chroma_db / 옵시디언 볼트 (2) memory_config.py wiki 패치 (3) brain_share 모듈 + brain_share_config.json (read_key / blocked_divisions) (4) RAG :9210 + 공유 게이트웨이(:9211) 살아있음 (5) `~/.claude/skills` + `~/.claude/plugins` 설치 여부 (6) 런타임 도구(graphify / yt-dlp / serena-agent). FAIL/WARN/OK 요약 + exit code.
- **`memory_mcp.py`** — 로컬 Claude 에서 자체 RAG(:9210)에 `recall_memory` / `save_memory` 두 도구를 노출하는 MCP 서버. **소유자 전용이라 민감정보 필터 없음**(정책 `personal-in-leaf-only`과 일치). memory_api 의 통합 `/memory/store` 라우트를 그대로 사용해 기존 컬렉션(`<agent>_*`) 유지. MCP 서버 이름은 `$AGENT_NAME` 기반(기본 `brain-memory`), `$MEMORY_MCP_NAME` env 로 명시 지정 가능.
- **`setup_obsidian.py`** — 옵시디언 볼트 자동 생성(`.obsidian/app.json`) + `brain_share_config.json`의 `vault_dir` 자동 갱신(백업 후) + 선택적 `--seed` 로 RAG 기억을 `_RAG_스냅샷/` 폴더에 브라우징 노트로 스냅샷. 기존 `.md`·`chroma_db` 는 절대 삭제·수정 안 함.

### 일반화
편입 시 특정 에이전트 이름 하드코딩을 전량 제거하여 어떤 브레인 키트 설치에도 통용되도록 수정:
- `memory_mcp.py` MCP 서버명·source 태그·stderr 배너 모두 `MCP_NAME` 변수로 통일 (`{AGENT_NAME}-memory` 파생).
- `setup_obsidian.py` 기본 `--root` = `C:\brainkit\memory` (표준 위치).
- `healthcheck.py` 이미 에이전트 무관하게 작성되어 있어 무변경.

### 검증
- 3파일 `py_compile` 통과.
- brain_share 기존 126 테스트 회귀 0 (신규 3파일은 통합 스크립트라 pytest 커버리지 밖 — 브레인 키트 설치 실행 후 사용).

### 위치
zip 안 `mokai_brain_kit/` 최상위 (install.py / setup_identity.py 와 동급). 설치 후 필요 시 사용자가 수동 실행.

---

## [3.1.2] - 2026-06-26

### 추가
- **`brain_share/selfsynth_batch.py`**: 에이전트의 자체 RAG 메모리(예: `<agent>_knowledge`)를 정본 위키로 합성하여 `<agent>_wiki` 컬렉션에 실적재하는 주기 batch. NoOpIndexer 대신 임베딩 주입형 `_WikiIndexer`로 통합검색 노출 가능.
  - `cluster_topics(emb, over_k, merge_threshold)` — over-cluster(KMeans) + 코사인 병합(Agglomerative) 자동 k.
  - `pick_representatives(emb, labels, topic, k)` — 토픽 중심에 가까운 청크 k개.
  - `run_selfsynth(source_collection, wiki_collection, vault_dir, embed_fn, llm_synth_fn, extractor_fn, graph_db_path, …)` — 1회 pass. 무거운 의존(chroma 컬렉션 객체·임베더·claude·extractor) 전부 주입형 → GPU/네트워크 없이 결정적 단위테스트.
  - 빈 LLM body 보호(synth_daemon과 동일 패턴): `wiki_store.upsert`가 `""` 반환 시 그 토픽 wikis_made/wiki_count에 안 잡힘. 다음 pass에서 재시도.

### 검증
- 8 신규 단위테스트(separates clusters / empty / single / reps / writes vault+collection / empty source / empty LLM body). 118+8 = **126/126** 통과.
- **김비서 실가동 검증** (2026-06-26): kim_knowledge 5396건 → 9 토픽 → 8 정본위키 합성·kim_wiki 컬렉션 8건 실적재·관계그래프 48노드 473엣지. chroma 직접쿼리 정확 매칭 입증("조이듀 운영" distance 0.17, "Worker API 함정" 0.13). 김비서 본체 주간 cron(매주 월 03:00) 등록.

### 알려진 한계
- 김비서 RAG :9210 검색 API에서는 wiki 결과 비노출 — 김비서 본체 리랭커/hybrid 튜닝 별개 이슈(`feedback_kim_rag_wiki_collection_invisible.md`). brain_share `selfsynth_batch` 모듈 자체와는 무관. 다른 에이전트의 RAG 구성이 다르면 그대로 노출됨.

---

## [3.1.1] - 2026-06-25

### 추가
- **`brain_share/leaf_registration.py`**: 메인 설치 직후 `LEAF_REGISTRATION.md`를 자동 생성. 안에는 새 하위 PC 등록에 필요한 4단계(패키지 설치 / MCP 등록 / 환경변수 / sync_agent 부팅등록) 명령이 메인의 실제 `read_key`와 함께 그대로 박혀 있어 복붙 한 번으로 끝남. 멱등 — 이미 있으면 read_key 재발급 0.
- **`install.py --main-host` 옵션**: 메인 IP/도메인을 LEAF_REGISTRATION.md에 박을 값. 미지정 시 `$BRAIN_MAIN_HOST` env 사용, 그것도 없으면 `<MAIN_HOST_IP_OR_DOMAIN>` 플레이스홀더(운영자가 1회 수정).
- **UX**: 메인 설치 후 사장님이 "하위 등록 명령 알려줘"·"leaf 등록 어떻게 했더라"라고 물으면 메인 김비서가 이 파일을 보여드림(CLAUDE.md 한 줄 안내 추가). 신규 PC 합류 절차가 "메인에 물어보고 복붙"으로 단일화.

### 검증
- 4 신규 단위테스트(render 콘텐츠·idempotent·placeholder·디렉토리 자동 생성). 114 + 4 = **118/118** 통과.

---

## [3.1.0] - 2026-06-25

### 추가 — 양방향 지식교환 완성 (하위→메인 업로드 파이프라인)
- **`brain_share/intake_filter.py`**: 순수 검증 게이트(`validate_incoming`) — 민감 재검·중복·품질 3중 필터. 자동통합 파이프라인의 마지막 누설 방어선. `compute_item_id(node_id, content)`는 null-byte 구분자로 해싱(`a||bc` vs `ab||c` 충돌 회피).
- **`brain_share/intake_server.py`**: 메인 수신 서버 `:9212` (읽기 게이트웨이 `:9211`과 별도 프로세스). 공용 읽기 키 + `node_id` 인증(`hmac.compare_digest`), 통과분만 `incoming/<node_id>/<id>.json` 저장 + 선택적 RAG 인덱싱. 기본 바인딩 `127.0.0.1`, LAN 노출은 `BRAIN_SHARE_INTAKE_HOST` env opt-in. `node_id`·`item.id` 경로횡단 차단(`[A-Za-z0-9_-]{1,64}` / `[A-Za-z0-9]{1,64}`).
- **`brain_share/sync_agent.py`**: 하위 PC 상주 동기화 에이전트(가벼움, LLM/임베딩/chroma 의존 0). SQLite 큐(WAL), 결정적 `item.id = sha256(node_id+content)[:16]`, 짧은 주기 flush(기본 180초), 시작 캐치업, 오프라인 시 큐 보존(network/non-200/malformed body 모두 큐 유지).
- **`brain_share/synth_daemon.py`**: 메인 주기 증분 정본화 데몬. `incoming/`를 topic별로 그룹핑하여 기존 `wiki_synth.synthesize_topic` 호출(claude/extractor 주입형). topic별 watermark로 신규분만 재합성. **LLM 빈 응답 시 watermark 미진전**(영구 토픽 손실 방어).

### 검증
- 4 신규 모듈 단위테스트 28건 + 종단테스트 2건. 79(기존) + 34(신규) = **113/113 통과**.
- 종단테스트가 "민감 item 누설 0" 실측 — 차단된 항목 메인 디스크 비도달 검증(파일 카운트가 아닌 실내용 substring 스캔).
- subagent-driven-development TDD로 6 Task 진행, 각 Task마다 sonnet 리뷰 + 발견 시 fix round. 리뷰가 잡은 핵심: (Task 2) `node_id`·`item.id` 경로횡단 + 시그니처 hmac.compare_digest, (Task 4) LLM 빈 응답 watermark 침묵 진전.

### 사용
```
# 메인(24h HUB)
python -m brain_share.intake_server --config brain_share_config.json --incoming C:/main_brain/incoming &
# 하위(자주 꺼지는 PC)
python -c "from brain_share.sync_agent import SyncAgent, SyncQueue; ..."
```
세부는 README §6 참고.

---

## [3.0.1] - 2026-06-25

### 수정 (epikx 실설치에서 발견된 6대 버그)
- **install.py — memory_config 패치 포맷감지**: 기존 코드는 `f"{AGENT_NAME}_wiki"`를 무조건 삽입하여 리터럴 형식(`"epikx_knowledge"`)의 memory_config에서 RAG 기동 시 `NameError: AGENT_NAME` 발생. 기존 `"knowledge"` 엔트리의 값 표현식을 클론하여 `knowledge → wiki`로 치환하는 방식으로 변경(리터럴/f-string/탭들여쓰기 모두 대응).
- **install.py — 콘솔 cp949 크래시**: em-dash 등 한글 외 유니코드에서 Windows 콘솔 cp949 인코딩 에러로 설치 중단. `sys.stdout/stderr.reconfigure(encoding="utf-8")` 강제.
- **install.py — bash 경로 escape 함정**: `--root C:\epikx\memory` 가 bash에서 `C:epikxmemory`로 둔갑하여 엉뚱한 폴더에 설치되던 사고. 드라이브 문자 뒤 구분자 없는 경로를 감지하여 사전 차단 + 슬래시 경로 사용 안내.
- **install.py — pytest 자동설치**: 의존성 목록에 pytest가 없어 step 8 테스트가 항상 ImportError로 실패. DEPS에 추가.
- **install.py — vault_dir 하드코딩 → ROOT 파생**: `C:\brainkit\obsidian` 고정으로 모든 설치에서 잘못된 볼트 경로 생성. ROOT가 `…/memory`로 끝나면 형제 `…/obsidian`을, 아니면 `ROOT/obsidian`을 기본값으로 자동 설정.
- **install.py — blocked_divisions 빈 배열 침묵 위험**: README 3단계 누락 시 PII/시크릿 누설 가능. 빈 상태로 패키지 생성 시 시각적으로 두드러진 보안 경고 출력.
- **gateway_mcp.py — host 0.0.0.0 LAN 노출**: 게이트웨이가 전 인터페이스 바인딩으로 LAN 무인증 노출 위험. 기본값을 `127.0.0.1`로 변경, 의도적 LAN 노출은 `BRAIN_SHARE_HOST=0.0.0.0` env로 명시.
- **mm_adapter.py — MEMORY_PATH 기본값 `C:/main_ai/memory` 제거**: 김비서 메모리 경로가 패키지에 박혀 있어 다른 에이전트에서 무심코 김비서 RAG를 로드할 위험. env 미설정 시 config 파일 경로의 부모 디렉토리에서 자동 유추, 그래도 없으면 명시적 에러.

### 변경
- config.py: `BrainShareConfig.source_path` 필드 추가(`load_config`가 자동 기록, mm_adapter가 MEMORY_PATH 자동 유추용으로 사용).

### 검증
- 79/79 테스트 통과(test_mm_adapter `source_path` 적용).
- memory_config 포맷감지 4 케이스(epikx 리터럴/kim 리터럴/f-string/탭들여쓰기) 전부 정확 변환 확인.

---

## [3.0.0] - 2026-06-22

### 추가
- 통합 브레인 공유 게이트웨이(MCP, 민감 누설0 필터)
- LLM wiki 합성 기능
- 토픽 자동도출
- 진화하는 관계 그래프(co-occurrence weight)
- 스킬 번들 6종(세레나·superpowers·graphify·karpathy·para-memory·youtube + 도구 자동설치)
- 정체성 설정(AGENT_NAME 이름지정 + CLAUDE.md 가이드라인, 멱등=기존 보존)

---

## [2.1.0] - 2026-06-14

### 변경
- config 단일 진실원천(AGENT_NAME 단일제어)
- export_to_obsidian 자동유도

---

## [2.0.0] - 2026-06-13

### 추가
- 기억이관
- Solo/Federated 2모드
- 피카추 흡수

---

## [1.0.0] - 2026-06-13

### 추가
- 최초 두뇌이식 (RAG+Obsidian+스킬+CLAUDE.md+워치독)
