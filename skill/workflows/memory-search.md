# Memory Search Workflow

## Purpose
시맨틱 + 시간 가중 검색으로 관련 메모리를 조회한다. 작업 시작 전, 구현 전, 오류 발생 시 과거 지식을 재활용하여 같은 실수를 반복하지 않는다.

## Trigger
- **Primary:** memory search, 메모리 검색
- **Secondary:** past findings, 과거 발견, recall, 기억 조회, similar patterns

## Tools
- `pkm memory search` (시맨틱 + 시간 가중 검색 CLI)

## Principles
- 세션 시작 시 항상 관련 과거 작업을 검색한다
- 구현 전 유사 패턴이 발견된 적 있는지 확인한다
- 오류 발생 시 과거 수정 레시피를 먼저 검색한다

## Edge Cases
- 결과가 없으면 검색어를 더 일반적으로 바꿔 재시도한다
- score 0.5 미만은 관련성이 낮을 수 있으니 주의해서 사용한다
- `--format json`으로 출력하면 파이프라인에서 활용하기 좋다

## Example Flow

```bash
# 1. 기본 시맨틱 검색
pkm memory search "authentication error"

# 2. 타입 필터
pkm memory search "database migration" --type procedural

# 3. 최근성 + 중요도 가중
pkm memory search "architecture decision" --recency-weight 0.4 --min-importance 7

# 4. 상위 20개 JSON 출력
pkm memory search "error handling" --top 20 --format json

# 5. 세션 시작 시 패턴
SESSION_TOPIC="auth refactor"
pkm memory search "$SESSION_TOPIC" --top 5
pkm memory search "$SESSION_TOPIC" --type procedural --top 3
```

## Scoring Formula

```
score = (1 - α) * semantic_similarity + α * recency_score * (importance / 10)
```

| `--recency-weight` | 동작 |
|-------------------|------|
| `0` (기본값) | 순수 시맨틱 유사도 |
| `0.5` | 시맨틱 + 최근성 균형 |
| `1.0` | 최근성 + 중요도 위주 |

## Output Formats

| Format | 설명 |
|--------|------|
| `table` (기본값) | Score \| Type \| Importance \| Title 테이블 |
| `plain` | `score path title` 한 줄씩 |
| `json` | 전체 구조화 출력, 파이프 활용 가능 |

## Expected Output
- 관련 메모리 목록 (점수순 정렬)
- 각 항목: 유사도 점수, 타입, 중요도, 제목, 경로
