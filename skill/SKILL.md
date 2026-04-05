---
name: pkm
description: "Personal Knowledge Management for Obsidian vaults — Zettelkasten workflow with daily notes, atomic notes, wikilinks, and a Python CLI tool (pkm). Use this skill whenever the user mentions: daily notes, 데일리 노트, note management, 노트 정리, knowledge extraction, 지식 추출, Zettelkasten, 제텔카스텐, note search, backlinks, wikilinks, PKM, 노트 검색, 노트 작성, or wants to create/update/search notes in their Obsidian vaults. Also trigger when the user says /pkm. Workflow triggers: dream, 노트 정리, 주간 리뷰, weekly review, 1:1 준비, 건강도, health check, 연결 찾기, 태스크 동기화, 작업기억, 미분류 정리, 오늘 시작, 월간 종합."
---

# PKM — Personal Knowledge Management

Obsidian 볼트 기반 제텔카스텐 지식 관리 시스템. 데일리 노트를 지식의 진입점으로 사용하고, 원자 노트로 지식을 정제하며, wikilink로 지식의 네트워크를 구축한다.

## Vault Structure

모든 볼트는 아래 표준 구조를 따른다:

```
<vault>/
├── daily/              # YYYY-MM-DD.md — 시간순 기록
├── notes/              # 플랫 구조의 제텔카스텐 원자 노트
├── tasks/              # ongoing.md + task-<slug>.md
│   └── archive/        # 완료된 태스크
└── data/               # 노트 첨부파일
```

볼트는 `PKM_VAULTS_ROOT` (기본: `~/vaults`) 하위에서 자동 발견된다. `daily/` 또는 `notes/` 디렉토리가 있으면 볼트로 인식한다.

## Core Workflow

```
[경험/학습] → daily/ (시간순 기록) → 반복·구조화 가치 발견 → notes/ (원자 노트 승격)
                                                              ↕ [[wikilink]] 연결
                                                         notes/ ↔ notes/ (지식 네트워크)
                                                              |
                                               pkm search (시맨틱 검색)
                                               workflows/ (자동화된 지식 관리)
```

### 1. Daily Note — 지식의 진입점

당일 경험, 학습, 아이디어를 시간순으로 기록한다. 완벽하지 않아도 된다 — 기록이 먼저다.

```markdown
---
id: 2026-04-05
aliases: []
tags:
  - daily-notes
---
- [09:30] 오늘 배운 것: ...
- [14:20] 미팅에서 나온 아이디어: ...

## TODO
- [09:30] 할 일 항목
```

### 2. Atomic Note — 정제된 지식

데일리에서 반복되거나 구조화할 가치가 있는 지식을 원자 노트로 승격한다.

**원칙:**
- **원자성**: 하나의 노트 = 하나의 주제. 여러 주제를 섞지 않는다.
- **연결**: 모든 노트는 `[[wikilink]]`로 관련 노트에 연결. 고립된 노트는 죽은 지식이다.
- **자기 언어**: 복사-붙여넣기가 아닌, 핵심을 이해하고 간결하게 서술한다.
- **플랫 구조**: `notes/` 내 폴더 중첩 없이 태그로 분류한다.

```markdown
---
id: <filename-without-extension>
aliases:
  - <short alias>
tags:
  - <topic-tag>
---

내용...

관련: [[YYYY-MM-DD]] (첫 학습), [[related-concept]]
```

### 3. Knowledge Extraction — 승격 판단 기준

데일리 노트에서 원자 노트로 승격할 때의 판단 기준:

- **반복성**: 같은 주제가 3일 이상 데일리에 등장하면 승격 후보
- **참조 가능성**: 다른 맥락에서 참조할 가치가 있는 독립적 지식
- **구조화 가치**: 산발적 메모를 하나의 개념으로 정리할 수 있을 때
- **연결 가능성**: 기존 원자 노트와 의미 있는 연결이 가능할 때

## CLI Tool: `pkm`

Python CLI tool at `~/.claude/skills/pkm/scripts/pkm-cli/`. Install with:

```bash
cd ~/.claude/skills/pkm/scripts/pkm-cli && uv pip install -e ".[search]"
```

### Configuration

```bash
export PKM_VAULTS_ROOT=~/vaults        # 볼트 루트 디렉토리 (기본: ~/vaults)
export PKM_DEFAULT_VAULT=<vault-name>  # 기본 볼트 (미설정 시 첫 번째 발견된 볼트)
```

### Commands (v0.1)

```bash
# Daily notes
pkm daily                          # Show/create today's daily note
pkm daily --vault <name>           # Specific vault
pkm daily add "학습 내용"           # Append timestamped entry
pkm daily todo "할 일"              # Add to TODO section

# Note creation
pkm new "Note Title" --tags t1,t2  # Create atomic note with frontmatter
pkm new "제목" --vault <name>      # In specific vault

# Maintenance
pkm orphans                        # Find notes with no wikilinks (dead knowledge)
pkm tags                           # List all tags with counts
pkm stats                          # Vault statistics
pkm stale --days 30                # Notes not updated in 30+ days
```

### Design Principles

- **No database** — 파일이 유일한 진실의 원천. Obsidian과 충돌 없음
- **볼트 자동 발견** — 하드코딩 없이 디렉토리 구조로 볼트를 인식
- **한국어 네이티브** — 파일명, 본문, 검색 모두 한국어 지원

When helping the user, prefer using the CLI tool for automation. For interactive knowledge work (writing, linking, extracting), work directly with the files using Read/Write/Edit tools.

## Workflows

PKM 워크플로우는 `workflows/` 폴더에 독립 문서로 정의된다. 사용자 요청에 맞는 워크플로우를 찾아 해당 문서를 읽고 실행한다.

| Workflow | Primary Trigger | 문서 |
|----------|----------------|------|
| Dream | dream | workflows/dream.md |
| Weekly Review | 주간 리뷰 | workflows/weekly-review.md |
| 1:1 Prep | 1:1 준비 | workflows/1on1-prep.md |
| Health Check | 건강도 | workflows/health-check.md |
| Connect | 연결 찾기 | workflows/connect.md |
| Task Sync | 태스크 동기화 | workflows/task-sync.md |
| Working Memory | 작업기억 | workflows/working-memory.md |
| Capture Triage | 미분류 정리 | workflows/capture-triage.md |
| Daily Seed | 오늘 시작 | workflows/daily-seed.md |
| Monthly Synthesis | 월간 종합 | workflows/monthly-synthesis.md |

사용자 요청이 위 트리거와 매칭되면 해당 `workflows/*.md`를 읽고 실행한다. 여러 워크플로우가 매칭될 수 있으면 사용자에게 어떤 것을 원하는지 확인한다.

## Workflow Extension Guide

새 워크플로우를 추가하려면:
1. `workflows/_template.md`를 복사하여 새 파일 생성
2. Purpose, Trigger, Tools, Principles, Edge Cases, Example Flow, Expected Output 작성
3. 위 Workflows 테이블에 항목 추가
4. references/principles.md에 관련 노하우 축적

좋은 워크플로우의 기준:
- pkm CLI 명령어 또는 파일 도구로 실행 가능
- 에이전트 재량을 존중 (과도한 단계 지시 금지)
- 명확한 결과물 정의
- 반복 실행 시 일관된 품질
- 고유한 Primary Trigger (다른 워크플로우와 겹치지 않을 것)

## Principles & Know-how

Accumulated PKM principles and patterns are in `references/principles.md`. Read it when making decisions about note structure, tagging strategy, or knowledge organization. This file grows over time as we discover what works.

Read `references/workflows.md` for specific workflow patterns and automation recipes.

## Task Checklist

When the user asks for PKM help, follow this flow:

1. **Identify intent**: daily logging, note creation, knowledge extraction, or maintenance?
2. **Choose vault**: Infer from context if not specified. Use `--vault` flag or `PKM_DEFAULT_VAULT`.
3. **Check existing notes**: Search before creating — avoid duplicates.
4. **Maintain connections**: Every new note must link to at least one existing note.
5. **Use appropriate tool**: CLI for automation/batch, direct file ops for interactive work.
