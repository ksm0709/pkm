# Tag Explore — 태그 인덱스 탐색

## Purpose
태그를 인덱스 카드로 활용하여 주제별 지식을 탐색하고, 태그 노트에 설명을 추가하여 지식 네트워크의 진입점을 구축한다.

## Trigger
- **Primary:** 태그 탐색, tag explore
- **Secondary:** 태그 검색, 태그 정리, 인덱스 노트, 주제별 정리

## Tools
- `pkm tags` — 전체 태그 목록 + 사용 횟수 조회
- `pkm tags show <tag>` — 태그 노트 내용 + 해당 태그를 가진 노트 목록
- `pkm tags edit <tag>` — 태그 노트를 에디터로 열기
- `pkm tags search <pattern>` — 태그 패턴 검색 (glob, AND, OR)

## Principles
- **태그는 인덱스 카드다**: 단순 분류가 아니라 해당 주제의 진입점. 태그 노트에 주제 개요, 핵심 개념, 관련 링크를 적어 지식 탐색의 출발점으로 만든다.
- **Lazy creation**: 태그 노트는 `tags show` 시 자동 생성된다. 모든 태그에 설명을 쓸 필요 없이, 의미 있는 태그부터 점진적으로 채워 나간다.
- **교차 검색으로 발견**: AND/OR 검색으로 태그 간 교차점에서 새로운 연결을 발견한다.

## Edge Cases
- `pkm tags show`에 존재하지 않는 태그를 넣으면 빈 태그 노트가 생성됨 — 의도적 동작이나, 불필요하면 `tags/` 에서 삭제
- 태그명에 특수문자 (`../`, 공백 외 비허용 문자) 사용 시 에러 반환
- `pkm tags search "c++"` — 연속 `++`는 태그명으로 인식, 단일 `+`만 AND 연산자

## Example Flow

```bash
# 1. 현재 태그 현황 파악
pkm tags
# → database (5), python (3), postgresql (2), ...

# 2. 주요 태그의 인덱스 페이지 조회
pkm tags show database
# → 태그 노트 (빈 상태) + database 태그를 가진 5개 노트 목록

# 3. 태그 노트에 주제 개요 작성
pkm tags edit database
# → tags/database.md에 "데이터베이스 관련 노트 모음. 주요 주제: MVCC, 격리수준, 인덱싱" 등 작성

# 4. 교차 검색으로 관련 노트 발견
pkm tags search "database+postgresql"
# → 두 태그를 모두 가진 노트만 필터링

# 5. 유사 태그 계열 탐색
pkm tags search "data*"
# → database, data-pipeline, data-modeling 등 관련 태그의 노트
```

## Expected Output
- 주요 태그에 설명이 작성된 인덱스 노트 (`tags/*.md`)
- 태그 기반으로 주제별 노트 그룹이 파악된 상태
- 교차 검색으로 발견한 새로운 연결 관계
