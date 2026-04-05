# Dream — Daily-to-Knowledge Promotion

> **사전 준비:** `pkm consolidate`로 후보를 확인하고, `pkm consolidate mark YYYY-MM-DD`로 준비 완료 표시 후 이 워크플로우를 실행하세요. `consolidated: true`가 설정된 데일리만 처리합니다. 자세한 내용은 `workflows/consolidate.md`를 참고하세요.

## Purpose
최근 데일리 노트에서 영구 지식으로 승격할 인사이트를 발굴하고, 지식 베이스를 정리·연결한다.

## Trigger
- **Primary:** "dream"
- **Secondary:** "지식 승격", "데일리 정리", "인사이트 추출"

## Tools
- Read (`daily/*.md` — 최근 7일)
- `pkm new` (새 지식 노트 생성)
- Edit (wikilink 추가)
- `pkm orphans` (고아 노트 탐지)

## Principles
- 반복 등장하거나 행동 변화를 유발한 인사이트만 승격한다
- 기존 노트와 중복되면 신규 생성 대신 기존 노트를 보강한다
- 승격 후 원본 데일리에 `→ [[노트명]]` 링크를 남긴다

## Edge Cases
- 최근 7일 데일리가 없으면 범위를 14일로 확대하고 사용자에게 알린다
- `pkm new` 실패 시 Write 도구로 직접 파일을 생성한다
- 승격 후보가 0개이면 "승격할 인사이트 없음" 요약을 반환하고 종료한다

## Example Flow
1. `pkm consolidate` 실행 → 미통합 데일리 목록 확인
2. `consolidated: true` 가 있는 데일리는 건너뜀
3. Read `daily/2026-03-30.md` ~ `daily/2026-04-05.md` (7개 파일, 미통합 항목만)
4. 반복 키워드·패턴 식별 → 후보 목록 작성
   - 예: "비동기 오류 처리 패턴" 3일 연속 언급
5. `pkm search "비동기 오류"` → 기존 노트 확인
6. 없으면 `pkm new "비동기 오류 처리 패턴"` 실행
7. Edit으로 관련 노트에 wikilink 추가 (`→ [[노트명]]`)
8. `pkm orphans` 실행 → 새 노트가 고아인지 확인
9. **Prune**: 중복·오래된 노트 식별 후 병합 제안
10. **Atomize**: 2개 이상 주제를 담은 노트 분할 제안
11. **Connect**: 연결 없는 노트쌍 연결 제안
12. `pkm consolidate mark {date}` 실행 → 처리한 각 데일리를 통합 완료로 표시

## Expected Output
- 승격된 노트 목록 (제목, 경로)
- 병합/분할 제안 목록
- 새로 추가된 wikilink 목록
- 고아 노트 잔존 수
