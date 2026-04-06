# Capture Triage — Untagged Note Classification

## Purpose
frontmatter에 태그가 없는 노트를 찾아 적절한 태그를 제안하고 분류한다.

## Trigger
- **Primary:** "미분류 정리"
- **Secondary:** "태그 없는 노트", "capture triage", "노트 분류"

## Tools
- Grep (frontmatter `tags` 필드가 빈 노트 탐색)
- Read (노트 내용 확인)
- Edit (태그 추가)
- `pkm tags` (기존 태그 목록 확인)

## Principles
- 기존 태그 체계를 먼저 파악하고 그 안에서 분류한다 — 새 태그는 최소화한다
- 한 노트당 태그 3개 이하를 권장한다
- 내용을 읽지 않고 태그를 추가하지 않는다

## Edge Cases
- Grep 결과가 없으면 "미분류 노트 없음" 메시지 후 종료한다
- 내용이 너무 짧아 분류 불가한 경우 "#stub" 태그를 제안한다
- 태그 제안 후 사용자가 수정 요청하면 대안을 제시하고 재확인한다

## Example Flow
```
1. `pkm tags` → 현재 볼트의 태그 목록 파악
   예: #dev, #meeting, #idea, #book, #personal

2. Grep `notes/` for 빈 tags 필드:
   패턴: `tags:\s*\[\]` 또는 `tags:$`
   결과: ["메모-240315.md", "스크랩-리액트.md", "생각들.md"]

3. Read "메모-240315.md" → 내용: React 성능 최적화 관련 메모
   제안 태그: ["#dev", "#react"]

4. 사용자 확인:
   "'메모-240315.md'에 #dev, #react 태그를 추가할까요?"

5. 승인 시 Edit frontmatter 업데이트

6. 다음 노트로 반복
```

## Expected Output
- 태그 추가된 노트 목록 (노트명, 추가된 태그)
- 건너뛴 노트 목록 (이유 포함)
- 처리 후 잔존 미분류 노트 수
