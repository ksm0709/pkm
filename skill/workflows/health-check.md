# Health Check — Note Health Diagnostics

## Purpose
볼트 전체의 건강도를 진단하고 고아 노트, stale 비율, 태그 분포를 리포트한다.

## Trigger
- **Primary:** "건강도"
- **Secondary:** "health check", "볼트 진단", "노트 점검"

## Tools
- `pkm orphans` (연결 없는 고아 노트 목록)
- `pkm stale` (오래된 미수정 노트 목록)
- `pkm tags` (태그 분포 현황)
- `pkm stats` (전체 노트 통계)

## Principles
- 숫자는 판단이 아닌 측정이다 — 리포트는 현황만 기술한다
- 심각도 기준: 고아 노트 10% 초과 = 경고, 20% 초과 = 위험
- 리포트 후 즉각 수정하지 않고 사용자 판단을 기다린다

## Edge Cases
- `pkm stats`가 0을 반환하면 Glob으로 직접 파일 수를 카운트한다
- `pkm stale` 결과가 50개 초과면 상위 10개만 표시하고 "(+N개)" 표기
- 태그가 전혀 없는 볼트면 capture-triage 워크플로우를 권장한다

## Example Flow
```
1. `pkm stats` → 전체 노트 수, 최근 30일 활동 통계
2. `pkm orphans` → 고아 노트 수 및 목록
3. `pkm stale` → 90일 이상 미수정 노트 목록
4. `pkm tags` → 태그별 노트 분포
5. 건강도 점수 계산:
   - 고아율 = 고아 수 / 전체 수 × 100
   - stale율 = stale 수 / 전체 수 × 100
6. 리포트 생성
```

## Expected Output
```
## 볼트 건강도 리포트 — 2026-04-05

### 전체 통계
- 총 노트: 142개
- 최근 30일 신규: 18개
- 최근 30일 수정: 34개

### 고아 노트 (연결 없음)
- 수: 11개 (7.7%) — ⚠️ 주의
- 상위 항목: "React 훅 메모", "독서 기록 2025-12", ...

### Stale 노트 (90일+ 미수정)
- 수: 22개 (15.5%)
- 상위 항목: "Docker 설정 메모", "팀 회의록 2025-Q3", ...

### 태그 분포
- #dev: 58개 | #meeting: 23개 | #idea: 19개 | 태그없음: 12개

### 권장 액션
1. dream 워크플로우로 고아 노트 연결
2. stale 노트 5개 검토 (이번 주)
3. 태그 없는 12개 → capture-triage 실행
```
