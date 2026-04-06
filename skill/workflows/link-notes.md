# Connect — Link Discovery

## Purpose
의미적으로 유사하지만 연결되지 않은 노트쌍을 발견하고 사용자 승인 후 wikilink를 추가한다.

## Trigger
- **Primary:** "연결 찾기"
- **Secondary:** "링크 제안", "노트 연결", "고아 연결"

## Tools
- `pkm orphans` (연결 없는 노트 목록)
- `pkm search` (키워드 기반 유사 노트 탐색)
- Read (노트 내용 확인)
- Edit (wikilink 추가)

## Principles
- 의미적 유사성 기반으로 제안한다 — 태그가 같아도 내용이 다르면 연결하지 않는다
- 사용자 승인 없이 Edit을 실행하지 않는다
- 양방향 링크를 추가한다 (A→B, B→A 모두)

## Edge Cases
- `pkm orphans`가 빈 목록을 반환하면 "고아 노트 없음, 모두 연결됨" 메시지 후 종료
- 제안 후 사용자가 거부하면 해당 쌍을 건너뛰고 다음 후보로 이동
- Read 실패 시 Glob으로 파일 존재 여부 확인 후 경로 수정

## Example Flow
```
1. `pkm orphans` → 고아 노트 목록 획득
   예: ["메모-비동기-패턴.md", "독서-Clean-Code.md", ...]

2. "메모-비동기-패턴.md" Read → 핵심 키워드 추출: "async/await", "에러 처리"

3. `pkm search "async await 에러 처리"` → 유사 노트 탐색
   결과: "JavaScript-에러-처리-패턴.md" (score: 0.87)

4. 사용자에게 제안:
   "[[메모-비동기-패턴]] ↔ [[JavaScript-에러-처리-패턴]] 연결할까요?"

5. 승인 시: Edit 양방향 링크 추가
6. 다음 고아 노트로 반복
```

## Expected Output
- 연결된 노트쌍 목록 (몇 쌍 연결됨)
- 거부된 제안 목록
- 잔존 고아 노트 수
