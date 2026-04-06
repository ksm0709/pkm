# Add Workflow — Workflow Creation Wizard

## Purpose
Socratic 인터뷰로 새 PKM 워크플로우 요구사항을 완전히 구체화하고, ambiguity/stability 측정으로 품질을 보증한 뒤 파일을 생성·배포한다.

## Trigger
- **Primary:** add-workflow, 워크플로우 추가, 새 워크플로우
- **Secondary:** workflow 만들기, 커스텀 워크플로우

## Tools
- AskUserQuestion (Socratic 인터뷰 — 한 번에 질문 1개)
- Read (`skill/workflows/` — 기존 워크플로우를 실제 예시로 참조)
- Write (`skill/workflows/<name>.md`, `skill/commands/pkm/<name>.md`)
- Edit (`skill/SKILL.md`)
- Bash (`cp ~/.claude/commands/pkm/` 즉시 배포)

## Principles
- 질문은 **한 번에 1개**, AskUserQuestion으로 진행한다
- 매 라운드 후 ambiguity score를 계산하고 사용자에게 공개한다
- Ambiguity ≤ 20% 가 될 때까지 인터뷰를 계속한다
- 기존 워크플로우를 예시로 보여주되, 사용자가 새로운 패턴을 발명하도록 장려한다
- 개념이 수렴하면(동일한 엔티티 2라운드 연속) 인터뷰를 마무리한다

## Workflow

### Phase 0: 소개

```
PKM 워크플로우 생성 마법사를 시작합니다.

Socratic 방식으로 질문하여 아이디어를 완전한 워크플로우 명세로 구체화합니다.
매 라운드 후 명확도(clarity)를 측정하고, 충분히 명확해지면 파일을 생성합니다.

현재 ambiguity: 100%
```

기존 워크플로우 목록을 보여준다:
```
현재 워크플로우:
  init-daily         — 오늘 데일리 노트 시작
  extract-note-from-daily — 데일리→원자 노트 승격
  weekly-review      — 주간 리뷰
  auto-tagging       — 태그 없는 노트 분류
  auto-linking       — 유사 노트 자동 연결
  health-check       — 볼트 건강도 진단
  tag-explore        — 태그 기반 지식 탐색
  backlink-traverse  — 백링크 기반 연결 탐색
  1on1-prep          — 1:1 미팅 준비
  task-sync          — TODO/태스크 동기화
  monthly-synthesis  — 월간 종합
  add-context-to-daily — 프로젝트 컨텍스트 기록
  (+ memory-* 시리즈)
```

### Phase 1: Socratic 인터뷰 루프

**Ambiguity 5개 차원 (워크플로우 설계 특화):**

| 차원 | 가중치 | 의미 |
|------|--------|------|
| Purpose Clarity | 30% | 이 워크플로우가 해결하는 문제가 명확한가? 기존 워크플로우와 차별화되는가? |
| Trigger Clarity | 20% | 언제 실행해야 하는지 구체적인 신호가 있는가? |
| Tool Coverage | 20% | 어떤 pkm 명령어/파일 도구를 써야 하는지 알고 있는가? |
| Flow Completeness | 20% | 실행 단계가 재현 가능한 수준으로 구체화됐는가? |
| Output Clarity | 10% | 완료 시 사용자가 받는 결과물이 명확한가? |

**Ambiguity 계산:**
```
clarity = purpose×0.30 + trigger×0.20 + tool×0.20 + flow×0.20 + output×0.10
ambiguity = 1 - clarity
```

**질문 전략:**
- 매 라운드: 가장 낮은 차원을 타겟으로 질문 1개
- 가장 낮은 차원과 그 이유를 먼저 명시한 뒤 질문한다
- 기존 워크플로우의 실제 예시를 보여주며 옵션을 제시한다
- 사용자의 답변에서 숨은 가정을 드러내는 질문을 한다

**인터뷰 형식 (매 라운드):**
```
라운드 {n} | 타겟: {weakest_dimension} | Ambiguity: {score}%

[weakest_dimension이 낮은 이유 한 줄]

{질문}
```

**pkm 기능 레퍼런스 (Tool Coverage 질문 시 제시):**
```
CLI 명령어:
  pkm daily                       — 오늘 데일리 조회/생성
  pkm daily add "내용"            — 타임스탬프 항목 추가
  pkm daily todo "할 일"          — TODO 추가
  pkm note add "제목" --tags t,t2 — 원자 노트 생성
  pkm note show <검색어>          — 노트 조회 + 백링크
  pkm note links <검색어>         — 백링크 전용
  pkm note edit <검색어>          — 에디터로 열기
  pkm note orphans                — 고립 노트 목록
  pkm note stale --days 30        — 오래된 노트
  pkm tags                        — 태그 목록 + 카운트
  pkm tags show <태그>            — 태그별 노트 목록
  pkm tags search "python+ml"     — AND/OR/glob 태그 검색
  pkm vault list                  — 볼트 목록
  pkm search <검색어>             — 시맨틱 검색 (index 필요)
  pkm index                       — 검색 인덱스 빌드
  pkm stats                       — 볼트 통계
  pkm consolidate                 — 승격 대상 데일리 목록
  pkm consolidate mark YYYY-MM-DD — 승격 준비 완료 표시

파일 도구:
  Read / Write / Edit             — 노트 직접 조작
  Glob                            — 파일 패턴 검색
  Grep                            — 내용 검색
```

**기존 워크플로우 예시 (참고용):**

`health-check` Tools 예시:
```
- pkm stats
- pkm note orphans
- pkm note stale --days 30
- pkm tags
```

`extract-note-from-daily` Flow 예시:
```
1. pkm consolidate → 미통합 데일리 확인
2. Read daily/*.md (consolidated: true 항목)
3. 반복 키워드 식별 → 승격 후보 목록
4. pkm search → 기존 노트 중복 확인
5. pkm note add → 새 원자 노트 생성
6. Edit → wikilink 추가
7. pkm consolidate mark → 완료 표시
```

**수렴 추적 (Concept Stability):**

매 라운드 현재 워크플로우 개념의 핵심 요소를 추출한다:
- Core Problem (해결하는 문제)
- Primary Action (주요 동작)
- Key Entities (노트, 태그, 데일리 등)

직전 라운드와 비교하여 stability_ratio를 계산:
```
stability_ratio = stable_elements / total_elements
```

2라운드 연속 stability ≥ 0.8 이면 개념이 수렴한 것으로 판단.

**라운드 완료 후 보고:**
```
라운드 {n} 완료.

| 차원 | 점수 | 가중치 | 기여 | 미확정 내용 |
|------|------|--------|------|------------|
| Purpose     | {s} | 30% | {s*0.3} | {gap or "명확"} |
| Trigger     | {s} | 20% | {s*0.2} | {gap or "명확"} |
| Tool        | {s} | 20% | {s*0.2} | {gap or "명확"} |
| Flow        | {s} | 20% | {s*0.2} | {gap or "명확"} |
| Output      | {s} | 10% | {s*0.1} | {gap or "명확"} |
| **Ambiguity** | | | **{score}%** | |

개념 수렴: {stable}/{total} 요소 안정 (stability: {ratio})

다음 타겟: {weakest_dimension} — {이유}
```

**조기 종료 조건:**
- Ambiguity ≤ 20% → 자동으로 Phase 2로 진행
- 3라운드 이후 사용자가 "충분해", "만들어줘" 등을 말하면 경고 후 확인
- 10라운드: 소프트 경고 ("현재 ambiguity {score}%. 계속하겠습니까?")

**Challenge 모드 (창의성 강화):**
- 라운드 4+: "이 워크플로우가 없다면 지금 어떻게 같은 목적을 달성하나요?" → 불필요한 복잡성 제거
- 라운드 6+: "가장 단순한 버전은 무엇일까요?" → 핵심 정제
- 라운드 8+ (ambiguity > 0.3): "기존 워크플로우 중 가장 비슷한 건 무엇인가요? 그것과 다른 점이 무엇인가요?" → 차별화 명확화

### Phase 2: 명세 확정 및 파일 생성

수집한 내용을 요약하여 확인받는다:
```
워크플로우 명세 (Ambiguity: {final_score}%)

이름: <name>
목적: <purpose>
트리거: Primary — <primary> | Secondary — <secondary>
Tools: <tools>
원칙: <principles>
Flow: <n>단계
기대 출력: <output>
```

AskUserQuestion으로 확인:
- "이대로 생성하기"
- "이름 변경 후 생성"
- "인터뷰 계속하기"

확인 후 파일 생성:

**`skill/workflows/<name>.md`** (`_template.md` 구조 준수):
```markdown
# <Workflow Name>

## Purpose
<purpose>

## Trigger
- **Primary:** <primary trigger>
- **Secondary:** <secondary triggers>

## Tools
<bullet list of pkm commands and file tools>

## Principles
<bullet list of principles>

## Edge Cases
<bullet list of edge cases>

## Example Flow
<numbered concrete steps>

## Expected Output
<output description>
```

**`skill/commands/pkm/<name>.md`**:
```markdown
Read `~/.claude/skills/pkm/workflows/<name>.md` and execute the workflow described there.
```

**`skill/SKILL.md`** 워크플로우 테이블에 행 추가:
```
| <Display Name> | <trigger keywords> | workflows/<name>.md |
```

**즉시 배포:**
```bash
mkdir -p ~/.claude/commands/pkm
cp skill/commands/pkm/<name>.md ~/.claude/commands/pkm/<name>.md
```

### Phase 3: 완료

```
✓ 워크플로우 생성 완료!

최종 Ambiguity: {score}%

생성된 파일:
  skill/workflows/<name>.md
  skill/commands/pkm/<name>.md

SKILL.md 업데이트 완료

즉시 사용 가능 (Claude Code 재시작 불필요):
  /pkm:<name>

저장소에 반영하려면:
  git add skill/ && git commit -m "feat: add <name> workflow"
```

## Edge Cases
- 이름이 기존 워크플로우와 충돌 → 다른 이름 제안
- Primary Trigger가 기존 워크플로우와 겹침 → 경고 후 확인
- `~/.claude/commands/pkm/` 없으면 자동 생성
- Ambiguity가 3라운드 연속 ±5% 이내로 정체 → "개념 자체를 재정의해봅시다" 리프레이밍

## Expected Output
- `skill/workflows/<name>.md` (완성된 워크플로우 명세)
- `skill/commands/pkm/<name>.md` (슬래시 커맨드 래퍼)
- `skill/SKILL.md` (테이블 업데이트)
- `~/.claude/commands/pkm/<name>.md` (즉시 배포)
