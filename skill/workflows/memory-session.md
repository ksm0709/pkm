# Memory Session Workflow

## Purpose
특정 에이전트 세션에 연결된 모든 메모리를 추적하고 조회한다. 세션 재개, 진행 감사, 작업 완료 후 통합 준비에 사용한다.

## Trigger
- **Primary:** memory session, 세션 메모리
- **Secondary:** session tracking, 세션 추적, session resume, 세션 재개

## Tools
- `pkm memory session` (세션 메모리 조회)
- `pkm memory store --session` (세션 태그 저장)
- `pkm consolidate` (세션 종료 후 통합 준비)

## Principles
- 세션 ID는 시작 시 한 번 생성하고 세션 내내 일관되게 사용한다
- 에피소딕 메모리는 항상 `--session` 플래그로 저장한다
- 세션 종료 시 `pkm memory session <id>`로 결과를 리뷰한다

## Session ID Convention

짧고 기술적인 슬러그 사용: `YYYY-MM-DD-task-name`

```bash
# 날짜 + 태스크명 기반
SESSION_ID="2026-04-05-auth-refactor"

# 자동 생성
SESSION_ID="$(date +%Y-%m-%d)-$(echo $TASK_NAME | tr ' ' '-' | head -c 20)"
```

## Edge Cases
- 세션 ID를 잊었으면 `pkm memory search` + 날짜 범위로 에피소딕 메모리를 찾는다
- 세션 메모리가 없으면 해당 세션에서 `--session` 플래그 없이 저장된 것일 수 있다
- 세션 종료 후 바로 통합할 필요는 없다 — `pkm consolidate`가 후보를 관리한다

## Example Flow

```bash
# 1. 세션 시작: ID 생성
SESSION_ID="2026-04-05-memory-layer-impl"

# 2. 작업 중: 에피소딕 메모리 저장
pkm memory store "WS-1 frontmatter 파싱 완료, edge case: BOM 헤더 처리 필요" \
  --type episodic --importance 6 --session $SESSION_ID

pkm memory store "sentence-transformers lazy import로 startup 1.2초 → 0.1초 개선" \
  --type procedural --importance 8 --session $SESSION_ID

# 3. 세션 종료: 결과 리뷰
pkm memory session $SESSION_ID

# 4. JSON으로 상세 조회
pkm memory session $SESSION_ID --format json

# 5. 통합 후보 확인 (선택적)
pkm consolidate
```

## Expected Output
- 세션에 연결된 메모리 목록 (타임스탬프순)
- 각 항목: 타입, 중요도, 제목, 저장 시각
- 세션 전체 메모리 수 요약
