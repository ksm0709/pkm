# Consolidate Workflow

## Purpose
통합 준비가 된 데일리 노트(에피소딕 메모리)를 식별하고 표시한다. PKM의 수면 통합에 해당 — 단기 에피소딕 기억을 장기 시맨틱 저장소로 이동하기 위한 준비 단계.

## Trigger
- **Primary:** consolidate, 통합
- **Secondary:** 데일리 통합, daily consolidation, memory consolidation, 메모리 통합

## Tools
- `pkm consolidate` (후보 목록 조회 — 읽기 전용)
- `pkm consolidate mark YYYY-MM-DD` (통합 준비 완료 표시)
- Dream 워크플로우 (`workflows/dream.md`) — 전체 야간 통합 파이프라인 (distill-daily 포함)

## Principles
- 통합은 2단계로 분리: 후보 확인 → 마킹. 데이터 손실 방지를 위해 절대 합치지 않는다
- 오늘 데일리는 항상 보호된다 — 절대 마킹하지 않는다
- 마킹은 멱등적: 같은 날짜를 두 번 마킹해도 안전하다

## Two-Phase Approach

```
Phase 1 (읽기 전용): pkm consolidate
  → 미통합 데일리 후보 목록 출력 (날짜, 항목 수)

Phase 2 (마킹): pkm consolidate mark YYYY-MM-DD
  → 해당 데일리 frontmatter에 consolidated: true 설정

Phase 3 (드림): Dream 워크플로우 실행
  → consolidated: true 데일리에서 원자 노트 추출
```

## Edge Cases
- 오늘 날짜 마킹 시도 → 오류 반환 (의도적 보호)
- distill-daily가 중간에 실패해도 `consolidated: true`는 설정되지 않음 → 다음 실행 시 재시도
- `consolidated: true`인 데일리는 후보 목록에서 제외됨

## Example Flow

```bash
# 1. 통합 후보 확인 (읽기 전용, 안전)
pkm consolidate
# 출력 예시:
# 2026-04-03 — 12 entries (unconsolidated)
# 2026-04-04 — 8 entries (unconsolidated)

# 2. 준비된 데일리 마킹
pkm consolidate mark 2026-04-03
pkm consolidate mark 2026-04-04

# 3. 마킹 후 distill-daily 워크플로우 실행
# → workflows/distill-daily.md 참고
```

## Safety Rules
- 오늘 데일리는 절대 마킹 불가 (활성 사용 중)
- 마킹은 `consolidated: true` frontmatter 설정만 수행 (내용 변경 없음)
- Dream 실패 시 마킹 상태는 유지되지 않음 — 안전하게 재시도 가능

## Expected Output
- 후보 목록: 날짜, 항목 수 (Phase 1)
- 마킹 확인: "consolidated: true set for YYYY-MM-DD" (Phase 2)
