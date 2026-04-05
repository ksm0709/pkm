# Memory Store Workflow

## Purpose
에이전트가 발견한 사실, 결정, 오류 해결책, 패턴을 PKM 볼트의 원자 노트로 저장한다. 이 노트들은 시맨틱 + 시간 가중 검색을 통해 재사용 가능한 장기 기억이 된다.

## Trigger
- **Primary:** memory store, 메모리 저장
- **Secondary:** remember this, 기억해, store finding, 발견 저장

## Tools
- `pkm memory store` (메모리 저장 CLI)
- `pkm memory search` (저장 전 중복 확인)

## Principles
- 저장 전 반드시 검색하여 중복을 방지한다
- 메모리 타입과 중요도를 명시적으로 지정한다
- 세션 추적이 필요하면 `--session` 플래그를 사용한다

## Memory Types

| Type | 언제 | 예시 |
|------|------|------|
| `semantic` | 안정적 지식, 사실, 패턴 | 아키텍처 결정, API 동작 |
| `episodic` | 세션 내 이벤트, 진행 상황 | "세션 X에서 로그인 버그 수정" |
| `procedural` | 방법론, 수정 레시피 | "Y를 수정하려면 Z를 하라" |

## Importance Scale

| 점수 | 의미 |
|------|------|
| 1-3 | 사소한, 낮은 가치 |
| 4-6 | 보통, 유용한 컨텍스트 |
| 7-8 | 중요, 재등장해야 함 |
| 9-10 | 핵심, 항상 관련됨 |

## Edge Cases
- 유사한 메모리가 이미 있으면 새로 저장하지 말고 기존 노트를 보강한다
- 중요도 판단이 어려우면 5로 설정 후 나중에 조정한다
- stdin 모드는 멀티라인 내용에 사용한다

## Example Flow

```bash
# 1. 저장 전 중복 확인
pkm memory search "IndexEntry crash unknown fields" --top 3

# 2. 유사 항목 없으면 저장
pkm memory store "IndexEntry crash는 새 필드 추가 시 발생 — fix: load_index()에서 unknown fields 필터링" \
  --type procedural --importance 8

# 3. 세션 추적 포함 저장
pkm memory store "WS-1 frontmatter 구현 완료" \
  --type episodic --importance 5 --session 2026-04-05-memory-layer

# 4. 멀티라인 내용 (stdin)
cat << 'EOF' | pkm memory store --stdin --type semantic --importance 7
Generative Agents 점수 공식:
score = (1 - α) * cosine_similarity + α * recency * (importance / 10)
recency = 0.995^hours_elapsed
EOF
```

## Expected Output
- 저장된 노트 경로 (`memory/YYYY-MM-DD-<slug>.md`)
- 중복 경고 (유사 메모리 발견 시)
