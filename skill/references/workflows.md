# PKM Workflows

워크플로우는 `workflows/` 폴더에 독립 문서로 정의된다. 각 워크플로우는 Purpose, Trigger, Tools, Principles, Edge Cases, Example Flow, Expected Output을 포함한다.

## 워크플로우 목록

| Workflow | Primary Trigger | 문서 |
|----------|----------------|------|
| Dream | dream | ../workflows/dream.md |
| Weekly Review | 주간 리뷰 | ../workflows/weekly-review.md |
| 1:1 Prep | 1:1 준비 | ../workflows/1on1-prep.md |
| Health Check | 건강도 | ../workflows/health-check.md |
| Connect | 연결 찾기 | ../workflows/connect.md |
| Task Sync | 태스크 동기화 | ../workflows/task-sync.md |
| Working Memory | 작업기억 | ../workflows/working-memory.md |
| Capture Triage | 미분류 정리 | ../workflows/capture-triage.md |
| Daily Seed | 오늘 시작 | ../workflows/daily-seed.md |
| Monthly Synthesis | 월간 종합 | ../workflows/monthly-synthesis.md |

## 워크플로우 실행 방법

사용자 요청이 위 Primary Trigger와 매칭되면 해당 `workflows/*.md`를 읽고 지시에 따라 실행한다.

새 워크플로우 추가는 `SKILL.md`의 **Workflow Extension Guide** 참고.
