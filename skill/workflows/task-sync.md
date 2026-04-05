# Task Sync — Task Synchronization

## Purpose
데일리 노트의 TODO 항목과 `tasks/ongoing.md`를 동기화하여 태스크 추적을 일관되게 유지한다.

## Trigger
- **Primary:** "태스크 동기화"
- **Secondary:** "task sync", "할 일 동기화", "ongoing 업데이트"

## Tools
- Read (`tasks/ongoing.md`)
- Grep (`daily/*.md`에서 TODO 섹션 추출)
- Edit (`tasks/ongoing.md` 업데이트)

## Principles
- 데일리의 TODO가 원천(source of truth)이고 ongoing.md는 집계 뷰다
- 완료된 항목은 ongoing.md에서 "이번 주 완료" 섹션으로 이동한다
- 신규 항목은 사용자 확인 후 WIP 또는 TODO로 분류한다

## Edge Cases
- `tasks/ongoing.md`가 없으면 CLAUDE.md 템플릿으로 새로 생성한다
- 데일리 TODO가 없는 날짜는 건너뛴다
- 중복 항목은 날짜가 최신인 것을 유지하고 나머지는 제거한다

## Example Flow
```
1. Read `tasks/ongoing.md` → 현재 WIP/TODO 목록 파악

2. Grep `daily/` for "## TODO" → 최근 7일 TODO 수집
   발견: "- [ ] API 문서 작성" (2026-04-03)
         "- [x] 코드리뷰 완료" (2026-04-04)
         "- [ ] 배포 스크립트 검토" (2026-04-05)

3. 비교:
   - "API 문서 작성" → ongoing WIP에 없음 → 추가 제안
   - "코드리뷰 완료" → ongoing WIP에 있음 → 완료로 이동
   - "배포 스크립트 검토" → 신규 → TODO로 추가 제안

4. 사용자 확인 후 Edit `tasks/ongoing.md`
```

## Expected Output
- 업데이트된 `tasks/ongoing.md` (WIP/TODO/완료 섹션 갱신)
- 변경 요약:
  - 완료 이동: N개
  - 신규 추가: N개
  - 중복 제거: N개
