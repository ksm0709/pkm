# pkm — Personal Knowledge Management CLI

Obsidian 볼트 기반 제텔카스텐 지식 관리 CLI. 데일리 노트, 원자 노트, wikilink, 시맨틱 검색을 지원합니다.

## 설치

### 빠른 설치 (권장)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/taeho/pkm/main/cli/install.sh)
```

### Git에서 직접 설치

```bash
uv pip install "pkm[search] @ git+https://github.com/taeho/pkm#subdirectory=cli"
```

### 소스에서 설치

```bash
git clone https://github.com/taeho/pkm ~/repos/pkm
cd ~/repos/pkm/cli
uv pip install -e ".[search]"
```

## 초기 설정

```bash
pkm setup
```

- 의존성 선택 설치 (search: sentence-transformers ~500MB)
- vault 경로 설정
- Claude Code 스킬 자동 설치 (`~/.claude/skills/pkm/`)

## 주요 명령어

```bash
# 데일리 노트
pkm daily                          # 오늘의 데일리 노트
pkm daily add "학습 내용"           # 타임스탬프 항목 추가
pkm daily todo "할 일"              # TODO 섹션에 추가

# 노트 관리
pkm new "Note Title" --tags t1,t2  # 원자 노트 생성

# 시맨틱 검색
pkm index                          # 검색 인덱스 빌드
pkm search "MVCC 동시성"           # 시맨틱 검색

# Vault 관리
pkm vault list                     # vault 목록
pkm vault add <name>               # 새 vault 생성

# 유지보수
pkm orphans                        # 연결 없는 노트 찾기
pkm stats                          # vault 통계
pkm stale --days 30                # 오래된 노트
```

## 구조

```
pkm/
├── cli/          # Python 패키지 (pkm CLI)
├── skill/        # Claude Code 스킬 (SKILL.md, workflows, references)
└── README.md
```

## 개발

```bash
cd cli
uv pip install -e ".[search,dev]"
pytest tests/
```

## 버전

현재: v0.2.0
