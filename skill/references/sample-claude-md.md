# Sample CLAUDE.md — Memory Layer Integration

아래 스니펫을 프로젝트의 `CLAUDE.md`에 추가하면 에이전트가 PKM 메모리 레이어를 활용한다.

---

```markdown
## Memory Layer

이 프로젝트는 PKM 메모리 레이어를 사용하여 에이전트 지식을 영속화합니다.

### 작업 시작 전 (필수)
1. 관련 과거 지식 검색:
   ```bash
   pkm search "<현재 작업 키워드>" --top 5
   pkm search "<현재 작업 키워드>" --type procedural --top 3
   ```
2. score 0.6 이상 항목은 반드시 읽고 참고한다
3. 이전에 해결한 동일 오류가 있으면 그 방법을 먼저 시도한다

### 작업 중 (중요 발견 시)
```bash
# 오류 수정 후
pkm note add --content "<오류명> fix: <해결 방법>" --type procedural --importance 8

# 아키텍처 결정 후
pkm note add --content "<결정 내용> — 이유: <근거>" --type semantic --importance 7

# 세션 진행 상황
pkm note add --content "<완료 내용>" --type episodic --importance 5 --session $SESSION_ID
```

### 작업 완료 후
```bash
# 세션 메모리 리뷰
pkm search --session $SESSION_ID

# 통합 후보 확인
pkm consolidate
```

### 메모리 타입 가이드
- `procedural`: 수정 레시피, HOW-TO ("X를 고치려면 Y")
- `semantic`: 아키텍처 결정, API 동작, 패턴 ("Z는 이렇게 작동한다")
- `episodic`: 진행 상황, 세션 이벤트 ("오늘 A를 완료했다")

### 중요도 기준
- 7-8: 다음 세션에서 반드시 재검토해야 할 정보
- 5-6: 맥락으로 유용하지만 필수는 아닌 정보
- 9-10: 프로젝트 핵심 제약사항, 절대 놓치면 안 되는 결정
```
