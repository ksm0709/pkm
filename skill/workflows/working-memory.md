# Working Memory — Context Preservation

## Purpose
진행 중인 프로젝트의 컨텍스트를 오늘 데일리 노트에 기록하여 세션 간 작업기억을 보존한다.

## Trigger
- **Primary:** "작업기억"
- **Secondary:** "컨텍스트 보존", "작업 맥락", "working memory"

## Tools
- `pkm search` (진행 중 프로젝트 노트 탐색)
- Read (진행 중 프로젝트 노트)
- `pkm daily add` (오늘 데일리에 섹션 추가)

## Principles
- 지금 이 순간 중요한 것만 기록한다 — 전체 프로젝트 문서가 아니다
- "어디까지 했나", "다음 단계", "블로커"의 세 항목이 핵심이다
- 데일리에 추가하되 기존 내용을 덮어쓰지 않는다

## Edge Cases
- `pkm search`가 빈 결과를 반환하면 `tasks/ongoing.md`에서 WIP 항목을 읽는다
- 진행 중 프로젝트가 없으면 "현재 활성 프로젝트 없음" 메시지 후 종료한다
- `pkm daily add` 실패 시 오늘 데일리 파일을 Read 후 Edit으로 직접 추가한다

## Example Flow
```
사용자: "작업기억 저장"

1. Read `tasks/ongoing.md` → WIP 항목 확인
   예: "프로젝트-알파 API 연동"

2. `pkm search "프로젝트-알파"` → 관련 노트 탐색
   결과: "notes/2026-04-03-프로젝트-알파-설계.md"

3. Read 해당 노트 → 현재 상태 파악
   - 어디까지: "인증 모듈 완료, 데이터 레이어 진행 중"
   - 다음 단계: "Repository 패턴 구현"
   - 블로커: "DB 스키마 확정 대기"

4. `pkm daily add` 또는 Edit 오늘 데일리:
   ## 작업기억
   - 프로젝트: [[프로젝트-알파-API-연동]]
   - 어디까지: 인증 완료, 데이터 레이어 진행 중
   - 다음: Repository 패턴 구현
   - 블로커: DB 스키마 확정 대기
```

## Expected Output
오늘 데일리 노트에 추가된 `## 작업기억` 섹션:
- 프로젝트명 (wikilink)
- 현재 진행 상태
- 다음 단계
- 블로커 (있을 경우)
