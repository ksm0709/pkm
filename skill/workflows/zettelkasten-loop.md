# Zettelkasten Loop — Capture to Writing

## Purpose
데일리 캡처를 literature/permanent note로 승격하고, 명시적 링크와 구조 노트를 거쳐 글감까지 밀어 올리는 제텔카스텐 운영 루프를 실행한다.

## Trigger
- **Primary:** zettelkasten, 제텔카스텐
- **Secondary:** note loop, capture to write, 글감 만들기, 구조 노트, 연결 루프

## Tools
- `pkm daily`
- `pkm daily add`
- `pkm note add`
- `pkm note show <query>`
- `pkm note links <query>`
- `pkm note orphans`
- `pkm note stale --days 30`
- `pkm tags show <tag>`
- `pkm search <query>`
- File tools such as Read/Edit

## Principles
- 캡처는 가볍게, 승격은 엄격하게 한다.
- 새 note는 최소 1개의 기존 note와 명시적으로 연결한다.
- 태그는 입구로 쓰고, 핵심 관계는 wikilink와 문맥 문장으로 남긴다.
- structure note는 목록이 아니라 관점이 드러나는 지도여야 한다.
- permanent note는 완성본이 아니라 계속 유용해지도록 다듬는 자산이다.

## Edge Cases
- 데일리에 승격할 만한 항목이 없으면 억지로 note를 만들지 말고 캡처 품질만 점검한다.
- 이미 비슷한 note가 있으면 새로 만들지 말고 기존 note를 확장한다.
- 연결할 note가 전혀 없으면 source note와 daily note에 먼저 연결한 뒤, `pkm note orphans` 결과를 다음 리뷰에서 다시 본다.
- structure note 후보가 약하면 태그 인덱스로 충분한지 확인하고, 관점이 생길 때까지 생성을 미룬다.

## Example Flow
1. `pkm daily`로 오늘 캡처를 읽는다.
2. 항목을 둘로 나눈다.
   - 출처가 있는 배움: literature note 후보
   - 경험과 해석에서 나온 개념: permanent note 후보
3. `pkm search`로 중복을 확인한다.
4. 필요하면 `pkm note add`로 새 note를 만든다.
5. 아래 질문 중 최소 2개에 답하며 링크를 건다.
   - 무엇을 설명하거나 반박하는가?
   - 어떤 기존 note를 더 구체화하거나 일반화하는가?
   - 반례가 되는 note는 무엇인가?
   - 어떤 검색어/상황에서 다시 찾을까?
6. `pkm note links <query>` 또는 `pkm note show <query>`로 연결 상태를 점검한다.
7. 관련 note가 4개 이상 한 주제 아래 모이면 structure note를 만든다.
   - 각 링크 옆에 왜 중요한지 한 줄 설명을 적는다.
8. structure note가 충분히 조밀해지면 그 순서대로 글 초안을 만든다.
9. 마지막에 `pkm note orphans`와 `pkm note stale --days 30`를 확인해 후속 정리 대상을 뽑는다.

## Expected Output
- 승격된 literature/permanent note 목록
- 새로 추가한 wikilink 목록
- 필요 시 새 structure note 1개
- 다음 글감 후보 또는 후속 조사 질문
