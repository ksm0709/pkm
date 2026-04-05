# Daily Seed — Morning Startup

## Purpose
오늘 데일리 노트를 생성하고 어제의 이월 TODO와 작업기억을 포함한 시작 컨텍스트를 준비한다.

## Trigger
- **Primary:** "오늘 시작"
- **Secondary:** "daily seed", "아침 시작", "오늘 데일리", "데일리 시작"

## Tools
- Read (어제 데일리 노트)
- `pkm daily` (오늘 데일리 생성)
- `pkm daily todo` (이월 TODO 추가)

## Principles
- 어제의 미완료 항목만 이월한다 — 완료 항목은 가져오지 않는다
- 오늘 데일리가 이미 존재하면 덮어쓰지 않고 섹션만 추가한다
- 이월 항목이 3일 연속 미완료면 "#stale-todo" 표시를 추가한다

## Edge Cases
- 어제 데일리가 없으면 마지막 데일리를 찾아 이월한다
- `pkm daily` 실패 시 Write로 오늘 날짜 파일을 직접 생성한다
- 주말·공휴일 이후 첫 시작이면 금요일 데일리부터 이월한다

## Example Flow
```
사용자: "오늘 시작"

1. 오늘 날짜 확인: 2026-04-05 (일요일)
   → 금요일 2026-04-03 데일리를 참조

2. Read `daily/2026-04-03.md` → ## TODO 섹션 추출
   미완료: "- [ ] API 문서 작성"
           "- [ ] 배포 스크립트 검토"  (2일 연속)
   완료:   "- [x] 코드리뷰"

3. `pkm daily` → `daily/2026-04-05.md` 생성 (또는 존재 확인)

4. `pkm daily todo` 또는 Edit으로 이월 섹션 추가:
   ## TODO
   - [ ] API 문서 작성 (이월: 04-03)
   - [ ] 배포 스크립트 검토 (이월: 04-03, ⚠️ 2일째)

5. working-memory 워크플로우 연계 제안
```

## Expected Output
- 생성/확인된 오늘 데일리 파일 경로
- 이월된 TODO 목록 (이월 날짜 포함)
- 장기 미완료(3일+) 항목 경고 목록
