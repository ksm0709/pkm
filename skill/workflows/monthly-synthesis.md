# Monthly Synthesis — Monthly Synthesis

## Purpose
한 달간 생성·수정된 노트를 종합하여 주요 테마와 인사이트를 담은 월간 종합 노트를 생성한다.

## Trigger
- **Primary:** "월간 종합"
- **Secondary:** "monthly synthesis", "월간 리뷰", "이번 달 정리"

## Tools
- Glob (`notes/YYYY-MM-*.md` — 이번 달 노트)
- Read (월간 노트 내용 확인)
- `pkm note add` (종합 노트 생성)

## Principles
- 개별 노트를 복사하지 않고 패턴과 테마를 추출한다
- 종합 노트는 인덱스가 아닌 해석이다 — "이달의 핵심 발견"을 1-3개로 압축한다
- 종합 노트 파일명: `YYYY-MM-synthesis.md`

## Edge Cases
- 이번 달 노트가 5개 미만이면 "데이터 부족" 경고 후 진행 여부를 사용자에게 묻는다
- `pkm note add` 실패 시 Write로 직접 생성한다
- 이미 해당 월의 synthesis 노트가 존재하면 덮어쓰지 않고 Edit으로 업데이트한다

## Example Flow
```
사용자: "월간 종합" (2026-04-05 기준 → 2026-03 정리)

1. Glob `notes/2026-03-*.md` → 이번 달 노트 목록
   결과: 23개 파일

2. Read 각 노트의 첫 단락 + 태그 (전체 읽기는 생략)

3. 태그 빈도 집계:
   #dev: 12 | #architecture: 5 | #meeting: 4 | #idea: 2

4. 주요 테마 식별:
   - 비동기 아키텍처 패턴 (6개 노트)
   - 팀 온보딩 프로세스 (4개 노트)

5. `pkm note add "2026-03-synthesis"` → 파일 생성

6. 종합 노트 작성:
   - 핵심 발견 2-3개
   - 주요 테마별 노트 링크
   - 다음 달 이어갈 주제
```

## Expected Output
`notes/2026-03-synthesis.md` 파일:

```markdown
---
id: 2026-03-synthesis
aliases:
  - 2026년 3월 종합
tags:
  - synthesis
  - monthly
---

# 2026년 3월 종합

## 핵심 발견
1. 비동기 오류 처리는 레이어별로 분리해야 한다 → [[비동기-에러-처리-패턴]]
2. 온보딩 체크리스트가 실제 온보딩 시간을 40% 단축함

## 주요 테마
### 비동기 아키텍처 (6개 노트)
- [[async-await-패턴]], [[에러-경계-설계]], ...

### 팀 온보딩 (4개 노트)
- [[온보딩-체크리스트-v2]], ...

## 다음 달 이어갈 주제
- Repository 패턴 심화
- 성능 모니터링 설정
```
