# Mokai Brain Kit 3.1.1 — Mokai Brain Kit 3.1.1

변경 이력은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.

## 목적

기존 RAG 데이터(chroma_db), Obsidian 노트, 메모리 파일을 **절대 건드리지 않고** brain_share 기능(공유 게이트웨이 · LLM wiki · 관계 그래프)을 기존 메모리 위에 얹는 데이터 보존형 업그레이드입니다. 설치는 추가(ADD)만 합니다 — 삭제·덮어쓰기 없음.

---

## AI에게 줄 수 있는 설치 지시문 예시 (복붙용)

이 패키지로 브레인 키트를 업그레이드해. 과거 RAG 데이터는 절대 건드리지 말고 보존. install_agent.py 실행 후, 내 RAG의 실제 division을 조회해서 민감한 것(회계/매매/고객/시크릿 성격)을 brain_share_config.json의 blocked_divisions에 채우고, 게이트웨이를 기동한 뒤 누설 0을 검증해서 보고해.

---

## agent 에이전트 실행 절차

### 1단계 — 압축 해제

```
# 패키지 폴더를 작업 디렉토리에 압축 해제
unzip brainkit_upgrade_agent.zip -d C:\agent_upgrade\
cd C:\agent_upgrade\upgrade_package_agent
```

### 2단계 — 설치 실행

```
python install_agent.py
# 기본 메모리 루트: C:\brainkit\memory
# 다른 경로라면: python install_agent.py --root C:\agent\your_memory_path
```

설치 중:
- brain_share 모듈 16개 복사 (chroma_db·obsidian 비접촉)
- 테스트 파일 복사
- 의존성(numpy / scikit-learn / pyyaml / mcp) 자동 설치
- memory_config.py 에 wiki 컬렉션 자동 추가 (기존 항목 유지)
- brain_share_config.json 생성 (최초 1회, 이후 덮어쓰지 않음)
- 생성된 **read_key** 를 터미널에 출력 → 메모해 두기
- 기초 smoke 테스트 + pytest 자동 실행

### 3단계 — 내 RAG division 실측

로컬 RAG 서버(기본 127.0.0.1:9210)에 아래 쿼리를 날려 division 목록을 수집한다:

```bash
curl -s -X POST http://127.0.0.1:9210/memory/search \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"*\",\"top_k\":50,\"min_score\":0}" \
  | python -c "
import json, sys, collections
data = json.load(sys.stdin)
results = data.get('results', data.get('matches', []))
divs = collections.Counter(r.get('metadata',{}).get('division','(none)') for r in results)
for d, c in divs.most_common(): print(f'{c:4d}  {d}')
"
```

출력 예시:
```
 412  CUSTOMER
 320  SYSTEM
 210  HR
  80  ACCOUNTING
  50  FINANCE
```

### 4단계 — blocked_divisions 채우기

`C:\brainkit\memory\brain_share_config.json` 열기:

```json
{
  "blocked_divisions": []
}
```

위 목록 중 외부에 공유하면 안 되는 division(회계·매매·고객·시크릿 성격)을 채운다:

```json
{
  "blocked_divisions": ["ACCOUNTING", "FINANCE", "CUSTOMER"]
}
```

### 5단계 — 게이트웨이 기동

```bash
python -m brain_share.gateway_mcp \
  --config C:\brainkit\memory\brain_share_config.json
```

포트는 config의 `share_port`(기본 9211). 로그에 `Gateway listening on :9211` 확인.

### 6단계 — 누설 검증

게이트웨이가 뜬 뒤, 민감 키워드로 질의해서 0건이 돌아오는지 확인:

```bash
# 민감 키워드 예시
curl -s -X POST http://127.0.0.1:9211/query \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"api_key secret 회계 매매\"}"
```

결과가 비어있거나 score 0이면 누설 차단 정상.

### 7단계 — Startup 등록 (콘솔 숨김 VBS)

아래 내용으로 `start_gateway.vbs` 저장 후 시작 프로그램(shell:startup)에 넣기:

```vbscript
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python -m brain_share.gateway_mcp --config C:\brainkit\memory\brain_share_config.json", 0, False
Set WshShell = Nothing
```

### 8단계 — 베이스라인 대조로 데이터 보존 확인

`install_agent.py` 출력의 "[0] Baseline snapshot" 행과 "[6] Post-install" 행을 비교:

```
chroma_db files : 1234 → 1234  (OK unchanged)
obsidian .md    : 567  → 567   (OK unchanged)
```

숫자가 달라졌다면 즉시 조사(정상 설치라면 변동 없음).

---

## 롤백 방법

brain_share 기능만 제거하고 원래 상태로 되돌리려면:

```powershell
# 1. brain_share 모듈 제거
Remove-Item -Recurse -Force C:\brainkit\memory\brain_share
Remove-Item -Recurse -Force C:\brainkit\memory\brain_share_tests

# 2. 게이트웨이 설정 제거
Remove-Item C:\brainkit\memory\brain_share_config.json

# 3. memory_config.py 백업 복원 (wiki 줄 제거)
Copy-Item C:\brainkit\memory\memory_config.py.bak `
         C:\brainkit\memory\memory_config.py -Force
```

→ chroma_db, obsidian, 기타 메모리 파일은 **전혀 건드리지 않았으므로** 완전 원복됨.

---

## 정체성 설정 (이름·가이드라인)

에이전트에게 이름과 작업 지침(CLAUDE.md)을 부여합니다.
**멱등 동작**: 이미 이름/CLAUDE.md 가 있으면 자동으로 건너뜁니다 — 기존 정체성을 절대 덮어쓰지 않습니다.

### 실행

```bash
python setup_identity.py --name <에이전트이름> --role <회사또는역할>

# 예시
python setup_identity.py --name myagent --role "회사"
python setup_identity.py --name alba  --role "알바 관리 플랫폼"

# root(Claude 홈) 가 기본값(~/.claude)과 다른 경우
python setup_identity.py --name myagent --role "회사" --root "~/.claude"
```

### 동작 설명

| 상황 | 이름 설정 | CLAUDE.md |
|------|-----------|-----------|
| 처음 설정 (아무것도 없음) | `setx AGENT_NAME <이름>` 실행 | CLAUDE_TEMPLATE.md 기반으로 생성 |
| 이름/CLAUDE.md 이미 있음 | **SKIP** (기존 보존) | **SKIP** (기존 보존) |
| --name 미지정 | SKIP + 안내 출력 | 이름 없으면 'agent' 로 생성 |

설정 후 **Claude Code 재시작** 필수.

---

## 스킬 번들 포함

`skills_bundle/` 디렉토리에 Claude Code 스킬 **6종** + 설치 스크립트가 포함되어 있습니다.

| 경로 | 내용 |
|------|------|
| `skills_bundle/skills/` | **graphify** / karpathy-guidelines / para-memory-files / youtube-summary (4개 폴더) |
| `skills_bundle/plugins.zip` | superpowers + serena 플러그인 패키지 |
| `skills_bundle/install_skills.py` | 스킬 + 플러그인 + 런타임 도구 일괄 설치 스크립트 |
| `skills_bundle/SKILLS_README.md` | 스킬별 역할, 설치 요건, 함정 메모 |

스킬 6종: graphify(코드 지식그래프) · karpathy-guidelines · para-memory-files · youtube-summary · superpowers · serena

### 스킬 설치 방법

```bash
cd skills_bundle
python install_skills.py
# 다른 Claude 홈 경로면: python install_skills.py --claude-home "C:\Users\YourName\.claude"
```

설치 후 **Claude Code 재시작** 필수. 상세 내용은 `skills_bundle/SKILLS_README.md` 참조.

---

## 파일 구성 (전체)

| 파일 | 설명 |
|------|------|
| `brain_share/*.py` | brain_share 모듈 16개 |
| `brain_share_tests/*.py` | pytest 테스트 스위트 |
| `brain_share_config.example.json` | 설정 파일 예시 |
| `install_agent.py` | brain_share 설치 스크립트 |
| `setup_identity.py` | 에이전트 정체성 설정 (이름 + CLAUDE.md) — 멱등 |
| `CLAUDE_TEMPLATE.md` | CLAUDE.md 생성 템플릿 ({{AGENT_NAME}} · {{ROLE_DESC}} 치환) |
| `SHA256SUMS.txt` | 파일 무결성 검증용 해시 |
| `skills_bundle/` | 스킬 번들 6종 + 설치 스크립트 |

---

---

## 6. 양방향 지식교환 (3.1.0+)

읽기(`:9211`)에 더해 하위→메인 업로드(`:9212`)가 추가됐다. 통합 검색은 기존 `:9211` 그대로.

### 메인(24h HUB)

```bash
# 1) 수신 서버 (별도 프로세스)
python -m brain_share.intake_server \
    --config C:\brainkit\memory\brain_share_config.json \
    --incoming C:\brainkit\memory\incoming
# 기본 바인딩 127.0.0.1, LAN 노출은 BRAIN_SHARE_INTAKE_HOST=0.0.0.0

# 2) 정본화 데몬 (주기·증분, claude CLI 주입)
python -c "from brain_share.synth_daemon import run_daemon; ..."
```

### 하위(자주 꺼지는 PC)

`SyncAgent`를 부팅 시 백그라운드 실행. 새 기억은 짧은 주기(180s) flush + 시작 시 캐치업으로 자동 업로드.

```python
from brain_share.config import load_config
from brain_share.sync_agent import SyncQueue, SyncAgent

cfg = load_config(r"C:\brainkit\memory\brain_share_config.json")
q = SyncQueue(r"C:\brainkit\memory\sync_state.db")
a = SyncAgent(cfg, node_id="leaf1",
              intake_url="http://main-brain.lan:9212/intake", queue=q)
a.run_forever(period_seconds=180,
              source_iter_factory=lambda: my_source())  # iterator over new items
```

### 보안 체크

- `intake_server`는 기본 `127.0.0.1` 바인딩. LAN 노출은 `BRAIN_SHARE_INTAKE_HOST=0.0.0.0` 명시 + 키 강도 충분히.
- 하위가 실수로 민감 보내도 메인 `intake_filter`가 마지막 방어. **단, blocked_divisions/blocked_keyword_patterns/blocked_tag_patterns 채워야 동작.**
- `node_id`·`item.id`는 영숫자 + `[_-]`만 허용(경로횡단 차단). `compute_item_id`는 자동으로 16자 hex 생성.

---

*Mokai Brain Kit 3.1.1 — agent brain_share upgrade package*
