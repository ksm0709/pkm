# Backlink Traverse — 백링크 기반 지식 탐색

## Purpose
백링크를 따라가며 노트 간 연결 관계를 탐색하고, 고립된 노트를 발견하여 지식 네트워크의 밀도를 높인다.

## Trigger
- **Primary:** 백링크 탐색, backlink traverse
- **Secondary:** 연결 탐색, 지식 탐색, 노트 관계, 백링크 확인

## Tools
- `pkm note show <query>` — 노트 본문 + 하단 Backlinks 섹션 (description 포함)
- `pkm note links <query>` — 해당 노트의 백링크만 테이블로 조회
- `pkm note orphans` — 연결이 없는 고립 노트 찾기
- `pkm tags show <tag>` — 태그 기반 출발점에서 탐색 시작

## Principles
- **백링크는 "누가 나를 참조하는가"**: 노트 안의 wikilink는 "내가 무엇을 참조하는가", 백링크는 그 역방향. 둘을 함께 보면 노트의 전체 맥락이 보인다.
- **description으로 빠른 판단**: 백링크 목록에서 description이 있는 노트는 `제목 — description` 형태로 표시되어, 노트를 열지 않고도 관련성을 판단할 수 있다.
- **고립 노트 제로**: orphans는 죽은 지식이다. 정기적으로 확인하여 연결하거나 정리한다.

## Edge Cases
- 백링크가 없는 노트 — `note show`에서 Backlinks 섹션이 표시되지 않음 (정상)
- 태그 노트(`tags/*.md`)는 백링크 스캔 대상에서 제외됨 — lazy-created 파일이 카운트에 영향 주는 것 방지
- 대규모 볼트에서 `find_backlinks()`가 모든 .md 파일을 스캔하므로 느릴 수 있음 — 현재 규모에서는 문제 없음

## Example Flow

```bash
# 1. 태그 인덱스에서 출발
pkm tags show database
# → database 태그를 가진 노트 목록 확인
# → mvcc, database-isolation, concurrency-note 등

# 2. 핵심 노트의 연결 관계 파악
pkm note show mvcc
# → 본문 출력 후...
# Backlinks
#   · database-isolation
#   · concurrency-note — 동시성 제어 기법 비교 노트

# 3. 백링크를 따라 관련 노트 탐색
pkm note show database-isolation
# → 이 노트의 본문 + 백링크 확인
# → mvcc에서만 참조되고 있음을 발견

# 4. 백링크 전용 뷰로 빠르게 확인
pkm note links mvcc
# → Title | Description | Path 테이블로 한눈에 파악

# 5. 고립 노트 발견 → wikilink 추가
pkm note orphans
# → 연결이 없는 노트 목록
# → 관련 노트에 [[orphan-note]] wikilink 추가하여 네트워크 연결
```

## Expected Output
- 노트 간 연결 관계가 파악된 상태 (어떤 노트가 허브인지, 어떤 노트가 고립되어 있는지)
- 고립 노트에 wikilink가 추가되어 네트워크에 편입
- description이 작성되어 백링크 탐색 시 빠른 맥락 파악 가능
