# Add Workflow — Workflow Creation Wizard

## Purpose
인터뷰를 통해 새 PKM 워크플로우를 설계하고, 파일 생성 및 배포까지 자동으로 처리한다.

## Trigger
- **Primary:** add-workflow, 워크플로우 추가, 새 워크플로우
- **Secondary:** workflow 만들기, 커스텀 워크플로우

## Tools
- AskUserQuestion (인터뷰 질문)
- Read (`skill/workflows/` — 기존 워크플로우 참조)
- Write (`skill/workflows/<name>.md`, `skill/commands/pkm/<name>.md`)
- Edit (`skill/SKILL.md` — 워크플로우 테이블 업데이트)
- Bash (`cp` — ~/.claude/commands/pkm/ 즉시 배포)

## Principles
- 질문은 한 번에 하나씩, AskUserQuestion으로 진행한다
- 기존 워크플로우를 실제 예시로 보여주며 옵션을 제안한다
- 생성 후 즉시 `~/.claude/commands/pkm/`에 배포하여 재시작 없이 사용 가능하게 한다
- 파일명은 kebab-case, 고유한 Primary Trigger를 가져야 한다

## Workflow

### Step 1: 소개

다음과 같이 인사한다:

> **PKM 워크플로우 생성 마법사**
>
> 몇 가지 질문으로 새 워크플로우를 설계하겠습니다.
> 기존 워크플로우를 예시로 참고하면서 진행합니다.

### Step 2: 워크플로우 목적 인터뷰

**Q1 — 목적 (Purpose)**

AskUserQuestion으로 묻는다:
- 이 워크플로우가 해결하려는 문제가 무엇인지
- 예시 옵션: "특정 주제의 노트를 한눈에 모아보기", "회의 전 관련 노트 수집", "직접 입력" 등

목적이 확정되면 한 줄 요약문(Purpose)을 작성한다.

**Q2 — 트리거 키워드 (Trigger)**

사용자가 어떤 말을 할 때 이 워크플로우를 실행할지 물어본다.

기존 예시를 보여준다:
- `init-daily`: "오늘 시작", "데일리 시작"
- `extract-note-from-daily`: "dream", "지식 승격"
- `weekly-review`: "주간 리뷰"

Primary Trigger(고유 키워드 1개)와 Secondary Trigger(선택)를 받는다.

**Q3 — 사용할 PKM 기능**

어떤 pkm 기능을 활용할지 보여주며 선택하게 한다 (복수 선택 가능):

```
CLI 명령어 예시:
  pkm daily                    — 오늘 데일리 노트 조회/생성
  pkm daily add "내용"         — 타임스탬프 항목 추가
  pkm daily todo "할 일"       — TODO 추가
  pkm note add "제목" --tags t — 원자 노트 생성
  pkm note show <검색어>       — 노트 조회 + 백링크
  pkm note links <검색어>      — 백링크 전용 조회
  pkm note orphans             — 고립 노트 탐지
  pkm note stale --days 30     — 오래된 노트 조회
  pkm tags                     — 태그 목록
  pkm tags show <태그>         — 태그별 노트 목록
  pkm tags search "pattern"    — 태그 검색 (glob, AND, OR)
  pkm search <검색어>          — 시맨틱 검색 (pkm index 필요)
  pkm stats                    — 볼트 통계
  pkm consolidate              — 승격 대상 데일리 목록
  pkm consolidate mark <날짜>  — 승격 준비 완료 표시

파일 도구:
  Read / Write / Edit          — 노트 직접 읽기/쓰기/편집
  Glob                         — 파일 패턴 검색
  Grep                         — 내용 검색
```

기존 워크플로우 Tools 예시도 보여준다:
- `weekly-review`: pkm stats, pkm note stale, pkm note orphans
- `auto-tagging`: pkm note show, pkm tags, Edit

**Q4 — 핵심 원칙 (Principles)**

이 워크플로우 실행 시 지켜야 할 규칙이 있는지 묻는다.

예시:
- "같은 노트를 중복 생성하지 않는다"
- "반드시 wikilink로 기존 노트와 연결한다"
- "사용자 확인 후 파일을 수정한다"

없으면 생략 가능.

**Q5 — 엣지 케이스 (Edge Cases)**

예외 상황 처리를 묻는다:
- 검색 결과가 없을 때
- 대상 파일이 없을 때
- 여러 후보가 있을 때

없으면 생략 가능.

**Q6 — 실행 흐름 (Example Flow)**

구체적인 실행 단계를 함께 설계한다.
기존 워크플로우 예시(init-daily, extract-note-from-daily)를 참고로 보여주며
이 워크플로우의 단계를 물어본다.

**Q7 — 기대 출력 (Expected Output)**

완료 시 사용자가 받는 결과물을 물어본다:
- 생성된 노트 목록
- 요약 보고서
- 수정된 파일 목록 등

**Q8 — 이름 확정**

수집한 정보를 바탕으로 파일명 후보 2-3개를 제안하고 선택하게 한다.
- kebab-case 형식
- Primary Trigger와 일치하거나 연관된 이름
- 기존 이름과 중복 안 됨

### Step 3: 확인 및 생성

수집한 내용을 요약하여 보여준다:
```
워크플로우 이름: <name>
목적: <purpose>
트리거: <trigger keywords>
Tools: <selected tools>
```

사용자 확인 후 다음 파일들을 생성한다:

**1. `skill/workflows/<name>.md`**

`_template.md` 구조에 맞춰 작성:
```markdown
# <Workflow Name>

## Purpose
<purpose>

## Trigger
- **Primary:** <primary>
- **Secondary:** <secondary>

## Tools
<tools>

## Principles
<principles>

## Edge Cases
<edge cases>

## Example Flow
<numbered steps>

## Expected Output
<output description>
```

**2. `skill/commands/pkm/<name>.md`**

```markdown
Read `~/.claude/skills/pkm/workflows/<name>.md` and execute the workflow described there.
```

**3. `skill/SKILL.md` 워크플로우 테이블**

테이블에 새 행 추가:
```
| <Display Name> | <trigger keywords> | workflows/<name>.md |
```

### Step 4: 즉시 배포

생성 후 바로 배포한다:
```bash
cp skill/commands/pkm/<name>.md ~/.claude/commands/pkm/<name>.md
```

### Step 5: 완료 메시지

```
✓ 워크플로우 생성 완료!

생성된 파일:
  skill/workflows/<name>.md
  skill/commands/pkm/<name>.md

SKILL.md 업데이트 완료

즉시 사용 가능:
  /pkm:<name>

배포 포함 저장하려면:
  git add skill/ && git commit -m "feat: add <name> workflow"
```

## Edge Cases
- 이름이 기존 워크플로우와 충돌하면 다른 이름을 제안한다
- Primary Trigger가 기존 워크플로우와 겹치면 경고 후 확인을 받는다
- `~/.claude/commands/pkm/` 디렉토리가 없으면 생성 후 배포한다

## Expected Output
- `skill/workflows/<name>.md` (완성된 워크플로우 정의)
- `skill/commands/pkm/<name>.md` (슬래시 커맨드 래퍼)
- `skill/SKILL.md` (테이블 업데이트)
- `~/.claude/commands/pkm/<name>.md` (즉시 배포)
