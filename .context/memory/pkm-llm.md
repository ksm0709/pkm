---
title: PKM LLM 에이전트 메모리 레이어 아키텍처
date: 2026-04-05
tags:
  - pkm
  - llm-agent
  - memory-layer
  - architecture
  - hooks
---

# PKM LLM 에이전트 메모리 레이어 아키텍처

# PKM LLM 에이전트 메모리 레이어 아키텍처

PKM을 LLM 에이전트의 유일한 외부 메모리 저장소로 사용하는 아키텍처 결정 및 구현 계획.

## 핵심 결정

context-mcp의 메모리 레이어를 PKM으로 완전 대체한다. MCP 서버 없이 **CLI + Skill + CLAUDE.md/AGENTS.md + Hooks** 조합으로 구현.

## 메모리 아키텍처

```
에이전트
  ├── Context Window          (작업 중 활성 메모리)
  └── PKM Vault               (유일한 외부 저장소)
       ├── daily/             (단기 에피소딕 메모리)
       └── notes/             (장기 시맨틱 메모리)
```

Zettelkasten 구조가 메모리 타입을 자연스럽게 매핑:
- daily/ = episodic memory (시간순 로그)
- notes/ = semantic memory (원자적 지식)

## 구현 컴포넌트

### 1. CLI 명령 (에이전트가 직접 실행)
- `pkm memory store <content> --type episodic|semantic|procedural --importance 1-10 --session <id>`
- `pkm memory search <query> --recency-weight --min-importance --type`
- `pkm memory session <session_id>`
- `pkm consolidate` — 미통합 데일리 → dream 워크플로우

### 2. 자동 통합 엔진
트리거: 마킹 미완료(`consolidated: false`) + 1일 이상 경과 데일리
실행: `dream` 워크플로우 → 원자노트 생성 + 마킹 업데이트
오늘 데일리는 제외 (아직 업데이트 중)

### 3. 검색 개선 (Generative Agents 공식)
```
score = α·recency + β·importance + γ·cosine_similarity
recency = 0.995^(hours_since_created)
```

### 4. YAML Frontmatter 확장
```yaml
memory_type: episodic | semantic | procedural
importance: 1-10
session_id: "session-abc123"
agent_id: "claude-code"
source_type: agent_observation | user_input | reflection
consolidated: false
```

### 5. 훅 지원 (세션 경계 자동화)

| 툴 | 이벤트 | 설정 |
|----|--------|------|
| Claude Code | SessionStart, Stop | `~/.claude/settings.json` |
| Codex CLI | SessionStart, Stop | `~/.codex/hooks.json` |
| opencode | session.created, session.idle (plugin) | `.opencode/plugins/pkm-memory.js` |
| zeroclaw | ❌ lifecycle 훅 없음 | 미지원 |

```json
// 훅 설정 예시 (Claude Code / Codex 공통)
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "pkm agent hook session-start --format system-reminder"}]}],
    "Stop":         [{"hooks": [{"type": "command", "command": "pkm agent hook on-complete"}]}]
  }
}
```

`pkm setup hooks --tool claude|codex|opencode` 으로 자동 주입 가능.

### 6. 에이전트 가이드
- `CLAUDE.md` — Claude Code 전용 정책
- `AGENTS.md` — 툴 독립 공통 정책 (PKM 단독 메모리 강제)

## 갭 분석 요약

### Critical (추가 필요)
- memory_type/importance/session_id 메타데이터
- 시간 가중 검색
- 통합 엔진 (consolidation)
- 훅 시스템

### Partial (개선 필요)
- 검색: 의미론적만 → 시간+중요도 가중 추가
- 메타데이터: tags/aliases만 → 에이전트 필드 추가

### 제외 (범위 밖)
- 외부 Vector DB / Redis
- MCP 서버
- BM25 (의미론적으로 충분)

## 관련 노트
- [[dream 워크플로우]] — 통합 엔진이 재사용하는 기존 워크플로우
- [[PKM CLI 구조]] — 기반 코드베이스


## Related Notes

- [[dream 워크플로우]]
- [[PKM CLI 구조]]

## 훅 이벤트 확정 (2026-04-05 업데이트)

PKM 훅 이벤트는 3종: `session-start`, `turn-start`, `turn-end`
툴별 지원 가능한 이벤트만 사용, 나머지는 graceful skip.

| PKM 이벤트 | Claude Code | Codex CLI | opencode |
|-----------|-------------|-----------|----------|
| session-start | ✅ SessionStart | ✅ SessionStart | ✅ session.created |
| turn-start | ✅ UserPromptSubmit | ✅ UserPromptSubmit | ⚠️ tui.prompt.append |
| turn-end | ✅ Stop | ✅ Stop | ⚠️ session.idle |

skill + cli + md 조합만으로도 충분히 강력 — 훅은 자동화 편의 수단.
zeroclaw: lifecycle 훅 없음, 미지원.
