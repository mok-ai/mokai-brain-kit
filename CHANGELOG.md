# Mokai Brain Kit — 변경 이력 (CHANGELOG)

모든 주요 변경 사항을 이 파일에 기록합니다. [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 형식 준수.

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
