# pkm — Personal Knowledge Management CLI

Obsidian 볼트 기반 제텔카스텐 지식 관리 CLI. 데일리 노트, 원자 노트, wikilink, 시맨틱 검색을 지원합니다.

## 설치

### 빠른 설치 (권장)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ksm0709/pkm/main/cli/install.sh)
```

### 소스에서 설치

```bash
git clone https://github.com/ksm0709/pkm ~/repos/pkm
cd ~/repos/pkm/cli
uv tool install --editable ".[search]"
```

## 초기 설정

```bash
pkm setup
```

- 의존성 선택 설치 (search: sentence-transformers ~500MB)
- vault 경로 설정
- Claude Code 스킬 자동 설치 (`~/.claude/skills/pkm/`, `~/.agents/skills/pkm/`)

## 주요 명령어

```bash
# 데일리 노트
pkm daily                             # 오늘의 데일리 노트 출력 (서브노트 포함)
pkm daily add "학습 내용"              # 타임스탬프 항목 추가 (## TODO 위)
pkm daily todo "할 일"                 # TODO 섹션에 추가
pkm daily edit                        # 에디터로 오늘 데일리 노트 오픈
pkm daily edit --sub                  # 서브노트 생성 후 에디터로 오픈 (제목 프롬프트)
pkm daily edit --sub "회의"           # 서브노트 직접 생성 (daily/YYYY-MM-DD-회의.md)

# 노트 관리
pkm note add "Note Title" --tags t1,t2  # 원자 노트 생성
pkm note edit <query>                   # 제목 검색 후 에디터로 오픈
pkm note show <query>                   # 제목 검색 후 내용 출력
pkm note stale --days 30               # 30일 이상 미수정 노트
pkm note orphans                        # wikilink 없는 고립 노트

# 시맨틱 검색
pkm index                             # 검색 인덱스 빌드
pkm search "MVCC 동시성"              # 시맨틱 검색

# Vault 관리
pkm vault list                        # vault 목록
pkm vault add <name>                  # 새 vault 생성
pkm vault open <name>                 # 기본 vault 전환

# 설정
pkm config set default-vault <name>  # 기본 vault 설정
pkm config set editor "code --wait"  # 에디터 설정
pkm config get editor                # 현재 에디터 확인
pkm config list                      # 전체 설정 목록

# 유지보수
pkm stats                            # vault 통계
pkm tags                             # 태그 목록 및 사용 수

# 업데이트
pkm update                           # 최신 버전으로 업데이트
pkm update v1.0.0                    # 특정 버전으로 업데이트
```

## 서브노트 구조

데일리 노트는 서브노트를 지원합니다:

```
daily/
├── 2026-04-05.md           # 메인 데일리 노트
├── 2026-04-05-회의.md      # 서브노트
└── 2026-04-05-아이디어.md  # 서브노트
```

`pkm daily` 실행 시 메인 노트 아래에 모든 서브노트가 순차 출력됩니다.

## 에디터 설정

`pkm daily edit` / `pkm note edit`에서 사용할 에디터 우선순위:

1. `pkm config set editor <cmd>` 설정값
2. `$VISUAL` 환경변수
3. `$EDITOR` 환경변수
4. `nano` (기본값)

```bash
pkm config set editor "vim"
pkm config set editor "code --wait"
```

## LLM Agent Memory Layer

PKM doubles as a persistent memory layer for LLM agents (Claude Code, Codex, opencode, etc.). Agents store decisions, findings, and errors as atomic notes; semantic search retrieves relevant context at session start.

```bash
# Store a memory
pkm memory store "content" --type semantic --importance 7
pkm memory store "content" --type episodic --importance 5 --session my-session

# Search before storing (avoid duplicates)
pkm memory search "topic" --top 5

# Recall session memories
pkm memory session my-session

# Inject session context into agent prompt
pkm agent hook session-start --format system-reminder

# Set up hooks for your agent runtime
pkm agent setup-hooks --agent claude-code   # writes ~/.claude/settings.json
pkm agent setup-hooks --agent codex
pkm agent setup-hooks --agent opencode

# Consolidate daily episodic notes into semantic memories
pkm consolidate --run
```

See [`docs/agent-memory-policy.md`](docs/agent-memory-policy.md) for the full usage guide including importance scoring, memory types, and hook configuration.

## 구조

```
pkm/
├── cli/          # Python 패키지 (pkm CLI)
│   ├── src/pkm/
│   │   ├── commands/   # daily, note, vault, config, search, ...
│   │   └── ...
│   └── tests/
├── skill/        # Claude Code 스킬 (SKILL.md, workflows, references)
└── README.md
```

## 개발

```bash
cd cli
uv venv && uv pip install -e ".[search,dev]"
pytest tests/
```

## 버전

현재: v2.0.0
