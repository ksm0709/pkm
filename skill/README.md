# PKM Skill — Workflows Index

PKM 워크플로우 목록. 사용자 요청에 맞는 워크플로우를 찾아 해당 문서를 읽고 실행한다.

## Memory Layer Workflows (LLM Agent용)

| Workflow | Primary Trigger | 문서 | 설명 |
|----------|----------------|------|------|
| Memory Store | memory store | [workflows/memory-store.md](workflows/memory-store.md) | 에이전트 발견/결정을 원자 노트로 저장 |
| Memory Search | memory search | [workflows/memory-search.md](workflows/memory-search.md) | 시맨틱 + 시간 가중 메모리 검색 |
| Memory Session | memory session | [workflows/memory-session.md](workflows/memory-session.md) | 세션 범위 메모리 추적 및 조회 |
| Consolidate | consolidate | [workflows/consolidate.md](workflows/consolidate.md) | 데일리 통합 후보 식별 및 마킹 |
| Dream | dream | [workflows/dream.md](workflows/dream.md) | 통합된 데일리에서 원자 노트 추출 |

## Knowledge Management Workflows (사용자 인터랙티브)

| Workflow | Primary Trigger | 문서 | 설명 |
|----------|----------------|------|------|
| Weekly Review | 주간 리뷰 | [workflows/weekly-review.md](workflows/weekly-review.md) | 주간 지식 정리 및 연결 |
| 1:1 Prep | 1:1 준비 | [workflows/1on1-prep.md](workflows/1on1-prep.md) | 1:1 미팅 준비 |
| Health Check | 건강도 | [workflows/health-check.md](workflows/health-check.md) | 볼트 건강도 점검 |
| Connect | 연결 찾기 | [workflows/connect.md](workflows/connect.md) | 고아 노트 연결 |
| Task Sync | 태스크 동기화 | [workflows/task-sync.md](workflows/task-sync.md) | 태스크 동기화 |
| Working Memory | 작업기억 | [workflows/working-memory.md](workflows/working-memory.md) | 현재 작업 컨텍스트 관리 |
| Capture Triage | 미분류 정리 | [workflows/capture-triage.md](workflows/capture-triage.md) | 미분류 항목 정리 |
| Daily Seed | 오늘 시작 | [workflows/daily-seed.md](workflows/daily-seed.md) | 하루 시작 루틴 |
| Monthly Synthesis | 월간 종합 | [workflows/monthly-synthesis.md](workflows/monthly-synthesis.md) | 월간 지식 종합 |

## Memory Layer Architecture

```
[에이전트 발견] → pkm memory store → memory/YYYY-MM-DD-<slug>.md
                                              ↓
[세션 시작]    ← pkm memory search ← 시맨틱 + 시간 가중 검색
                                              ↓
[일일 통합]    → pkm consolidate mark → consolidated: true
                                              ↓
[지식 승격]    → dream workflow → notes/<atomic-note>.md
```

## Integration Snippets

- [CLAUDE.md 통합 예시](references/sample-claude-md.md)
- [AGENTS.md 통합 예시](references/sample-agents-md.md)
