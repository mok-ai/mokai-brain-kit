# Mokai Brain Kit — 변경 이력 (CHANGELOG)

모든 주요 변경 사항을 이 파일에 기록합니다. [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 형식 준수.

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
