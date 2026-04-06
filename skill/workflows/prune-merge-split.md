# Prune-Merge-Split — 노트 정제

> **dream에서 실행 시:** step 6으로 자동 호출됩니다. 이 워크플로를 단독으로도 실행할 수 있습니다.

## Purpose
지식 베이스의 노트 품질을 유지한다:
- **Prune**: 오래되고 연결 없는 stale 노트 제거
- **Merge**: 내용이 중복되는 노트쌍 병합
- **Split**: 여러 주제를 다루는 노트를 원자 노트로 분할

## Trigger
- **Primary:** "prune", "merge", "split", "정제", "prune-merge-split"
- **Secondary:** "중복 제거", "노트 병합", "노트 분할", "원자화", "stale 제거"

## Tools
- `pkm search` (유사 노트 탐색)
- `pkm orphans` (연결 없는 노트)
- Read, Edit, Write, Glob

## Principles
- **Prune 기준**: 마지막 수정 6개월+ 경과 AND 들어오는 링크 0개
- **Merge 기준**: 내용 유사도 80%+ 노트쌍
- **Split 기준**: 2개 이상 독립적 주제를 포함한 노트
- 삭제(Prune)는 목록만 보고 — 실제 삭제는 사용자 확인 후
- 병합(Merge)·분할(Split)은 자동 수행 (원본 내용 보존)

## Three Operations

### 1. Prune (제거)
stale 후보 식별:
1. `pkm orphans` → 링크 없는 노트 목록
2. 각 노트의 마지막 수정일 확인 → 6개월+ 필터
3. 후보 목록 보고 (dream에서는 목록만 / 단독 실행 시 삭제 확인)

### 2. Merge (병합)
중복 노트 통합:
1. `pkm search` + Read로 내용 유사 노트쌍 식별
2. 더 완전한 노트에 내용 통합
3. 병합된 노트는 `→ [[통합 노트명]]` redirect wikilink로 대체

### 3. Split (분할 / 원자화)
대형 노트 분해:
1. Read로 노트 구조 분석 → 독립 주제 식별
2. 각 주제별 새 원자 노트 생성 (`pkm note add` 또는 Write)
3. 원본 노트를 목차/링크 모음으로 변환

## Example Flow

```
1. pkm orphans → ["old-scratch-2023.md", "임시메모.md"]
2. 수정일 확인 → "old-scratch-2023.md" 8개월 경과 → Prune 후보
3. pkm search → "성능측정.md" ↔ "벤치마크-기록.md" 유사도 0.87 → Merge
4. Read "Docker-설정과-배포.md" → 2개 주제 발견 → Split
   → "Docker-설정.md" + "Docker-배포.md" 생성
   → 원본을 두 노트로의 링크 목록으로 변환

보고:
  Prune 후보: 1개 (삭제 대기)
  Merged: 1쌍 (성능측정 ← 벤치마크-기록)
  Split: 1개 (Docker-설정과-배포 → 2개)
```

## Edge Cases
- 후보가 없으면: "정제할 노트 없음 — 지식 베이스 건강함" 보고
- Merge 후 원본 삭제 실패 시: redirect wikilink만 추가하고 계속
- Split 시 새 파일 이름 충돌: 날짜 접미사 추가 (`노트명-2026-04.md`)

## Expected Output
- **Prune**: 후보 N개 (목록), 삭제됨 N개
- **Merge**: N쌍 병합 완료
- **Split**: N개 노트 분할 (생성된 파일 목록)
- 변경된 파일 전체 목록
