# Sample AGENTS.md — Memory Layer Integration

아래 스니펫을 프로젝트의 `AGENTS.md`에 추가하면 에이전트 팀이 공유 메모리를 활용한다.

---

```markdown
## Agent Memory Protocol

### Session Initialization
모든 에이전트는 작업 시작 전 반드시 다음을 실행한다:

```bash
# 1. 관련 메모리 검색
pkm memory search "$TASK_DESCRIPTION" --top 5
pkm memory search "$TASK_DESCRIPTION" --type procedural --top 3

# 2. 세션 ID 설정
export SESSION_ID="$(date +%Y-%m-%d)-$(echo $TASK_NAME | tr ' ' '-' | head -c 20)"
```

### During Work
중요한 발견은 즉시 저장한다 — 세션 종료까지 미루지 않는다:

```bash
# 오류 해결 시 (즉시 저장)
pkm memory store "오류명: 원인 및 해결 방법" --type procedural --importance 8

# 아키텍처 결정 시 (즉시 저장)
pkm memory store "결정 내용 — 근거" --type semantic --importance 7 --session $SESSION_ID
```

### Before Claiming Completion
작업 완료를 선언하기 전:

```bash
# 1. 세션 메모리 확인
pkm memory session $SESSION_ID

# 2. 저장되지 않은 중요 발견이 있으면 저장
# 3. 통합 후보 확인 (선택적)
pkm consolidate
```

### Shared Memory Rules
- 같은 오류를 두 번 보고하지 않는다 — 저장 전 검색 필수
- `importance >= 7`인 메모리는 팀 전체가 공유하는 지식으로 간주
- 에이전트 간 충돌하는 메모리 발견 시 더 최근 + 높은 중요도 우선
- 실험적/미검증 발견은 `importance <= 5`로 저장
```
