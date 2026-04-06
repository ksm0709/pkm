# Dream — Nightly Knowledge Consolidation

## Purpose
데일리 노트부터 지식 베이스 정제까지, 야간 정보 통합 전체 파이프라인을 자동 실행한다.
6개 sub-workflow를 순서대로 오케스트레이션하며, 각 step 실패 시 skip 후 계속 진행한다.

## Trigger
- **Primary:** "dream", "드림"
- **Secondary:** "야간 정리", "nightly consolidation", "전체 정리", "지식 정리 전체"

## Pipeline

```
[1/6] consolidate       — 미통합 데일리 마킹
[2/6] distill-daily     — 데일리 → 영구 노트 승격
[3/6] auto-linking      — 연결 없는 노트 wikilink 추가
[4/6] auto-tagging      — 미태그 노트 태그 추가
[5/6] health-check      — 고아/stale 노트 감지 및 보고
[6/6] prune-merge-split — stale 제거, 중복 병합, 대형 노트 분할
```

## Tools
- `pkm consolidate` / `pkm consolidate mark`
- `pkm note add`, `pkm search`, `pkm orphans`
- Read, Edit, Glob
- (각 step의 전용 도구는 해당 sub-workflow 참고)

## Principles
- 각 step은 독립적으로 실행 — 한 step 실패가 전체를 중단하지 않음
- 완료 후 반드시 step별 결과 요약 출력 (✓/⚠/✗)
- 노트 수정은 자동 수행 (사용자 승인 없음)
- 오늘 데일리는 절대 수정/마킹하지 않음

## Execution Protocol

각 step은 순서대로 실행한다. 실패 시:
1. 오류 메시지를 캡처하여 최종 요약에 포함
2. 다음 step으로 계속 진행
3. 모든 step 완료 후 통합 요약 출력

## Step References

| Step | Workflow | 설명 |
|------|----------|------|
| 1 | `workflows/consolidate.md` | 미통합 데일리 후보 확인 및 마킹 |
| 2 | `workflows/distill-daily.md` | 마킹된 데일리에서 영구 노트 추출·승격 |
| 3 | `workflows/auto-linking.md` | 연결 없는 노트쌍 wikilink 추가 |
| 4 | `workflows/auto-tagging.md` | 미태그 노트 자동 태그 |
| 5 | `workflows/health-check.md` | 고아·stale 노트 감지 및 보고 |
| 6 | `workflows/prune-merge-split.md` | stale 제거, 중복 병합, 대형 노트 분할 |

## Example Flow

```
/pkm:dream 실행

[1/6] consolidate...
  → workflows/consolidate.md 실행
  → 4개 데일리 마킹 완료 ✓

[2/6] distill-daily...
  → workflows/distill-daily.md 실행
  → 3개 영구 노트 생성 ✓

[3/6] auto-linking...
  → workflows/auto-linking.md 실행
  → 7개 wikilink 추가 ✓

[4/6] auto-tagging...
  → workflows/auto-tagging.md 실행
  → 12개 노트 태그 완료 ✓

[5/6] health-check...
  → workflows/health-check.md 실행
  → 고아 2개, stale 1개 발견 ✓

[6/6] prune-merge-split...
  → workflows/prune-merge-split.md 실행
  → 1개 병합, 1개 분할 ✓

✅ dream 완료
  [1] consolidate:       ✓ 4개 데일리 마킹
  [2] distill-daily:     ✓ 3개 노트 생성
  [3] auto-linking:      ✓ 7개 링크 추가
  [4] auto-tagging:      ✓ 12개 노트 태그
  [5] health-check:      ✓ 고아 2개 보고
  [6] prune-merge-split: ✓ 1개 병합, 1개 분할
```

## Edge Cases
- consolidate 대상 없음: "마킹할 미통합 데일리 없음" 후 step 2 진행
- distill-daily 승격 후보 없음: "승격할 인사이트 없음" 후 step 3 진행
- 모든 step 실패 시: 각 오류 요약 출력 후 개별 워크플로 수동 실행 안내
- 어떤 step도 작업이 없으면: "이미 최신 상태 — 모든 step 대상 없음" 보고

## Expected Output
- 각 step별 ✓/⚠/✗ 결과
- 생성/수정/발견된 항목 수
- 실패한 step의 오류 메시지 (있는 경우)
- 총 소요 시간 (선택)
