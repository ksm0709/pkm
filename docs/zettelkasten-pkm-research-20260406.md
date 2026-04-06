# Zettelkasten Research for PKM

Date: 2026-04-06

## Goal
Tae Kim의 제텔카스텐 글을 기준 텍스트로 삼고, 정석 자료와 교차 검증해 `pkm`에 바로 적용 가능한 워크플로우로 재구성한다. 핵심 질문은 하나다: `pkm`이 이미 가진 `daily -> note -> links -> search` 흐름을 어떻게 제텔카스텐의 실제 사고 루프로 강화할 것인가. [1][2][3][4]

## Executive Summary
이 글의 핵심은 “노트를 많이 쌓는 것”이 아니라 “짧게 쓰고, 연결하고, 구조화하고, 글로 밀어 올리는 반복 루프”다. Tae Kim의 글은 이를 3단계로 압축한다: 매일 이해 가능한 짧은 노트를 쓰고, 기존 노트와의 연결을 고민해 링크하고, 군집이 생기면 긴 글로 전환한다. [1]

교차 검증 결과, `pkm`은 이미 제텔카스텐의 중요한 기반을 갖고 있다. 데일리 캡처, 원자 노트, 백링크, 고아 노트 점검, 태그 인덱스, 의미 검색이 모두 있다. 하지만 “캡처 후 당일 연결”, “출처 기반 literature note와 concept 기반 permanent note의 분리”, “구조 노트에서 글쓰기”, “연결 질문을 기준으로 한 수동 링크 루프”는 문서화가 약하다. [2][3][5][6][7][8][9][10]

따라서 `pkm`에 바로 맞는 적용안은 새 기능 추가보다 운영 루프 명확화다. 추천 기본 루프는 `capture -> distill -> connect -> structure -> write`이며, 이 루프는 새 워크플로우 문서 `zettelkasten-loop`로 패키징할 수 있다. 핵심 원칙은 다섯 가지다: 개념 단위로 쪼개기, 자기 언어로 다시 쓰기, 태그보다 명시적 링크를 우선하기, 구조 노트에서 집필하기, 완성 노트가 아니라 계속 유용한 노트를 기르는 것이다. [1][2][3][4][5][6][7][8][9][10]

## Source Scope
- 기준 텍스트: Tae Kim, "제텔카스텐: 하루 메모 6장으로 혁신적인 아이디어를 만드는 방법" [1]
- 보강 자료: Ahrens 계열 정리, Zettelkasten Method 운영 글, Andy Matuschak의 evergreen notes 원칙 [2][3][4][5][6][7][8][9][10]

## Extracted Workflow from Tae Kim's Article

### 1. Capture only high-value ideas, but capture daily
원문은 루만의 사례를 통해 “하루 평균 6개”라는 선택 압력을 강조한다. 요지는 많이 수집하는 것이 아니라, 남길 가치가 있는 배움과 통찰만 짧게 남기는 것이다. 이 캡처는 사실, 해석, 주장, 경험에서 모두 올 수 있다. [1]

`pkm` 적용:
- 즉시 캡처는 `pkm daily add`.
- 할 일과 통찰은 분리하고 TODO는 `pkm daily todo`로 보낸다.
- 하루의 원시 캡처는 거칠어도 되지만, 승격 후보는 적게 유지한다.

### 2. Rewrite each idea so another person could understand it
Tae Kim 글의 첫 단계는 “다른 사람이 읽어도 이해할 수 있도록” 짧게 정리하는 것이다. Ahrens 계열 자료와 Matuschak 자료도 모두 자기 언어, 독립적으로 읽히는 노트, 개념 중심 노트를 강조한다. [1][3][6][7][8]

`pkm` 적용:
- 데일리에서 바로 복붙하지 말고 `pkm note add` 전에 한 번 재서술한다.
- 원자 노트는 하나의 개념만 다룬다.
- 제목은 검색용 라벨이 아니라 주장 혹은 개념 핸들이 되게 쓴다. [7][9]

### 3. Convert raw capture into two note classes
Tae Kim의 부록 C는 실천 루프를 더 구체화한다. 출처가 있는 메모는 literature note, 그 외의 생각은 permanent note로 쓴다. [1] Zettelkasten Method 쪽 설명도 literature note와 permanent note를 엄격한 위계보다 “미래에 유용하게 남는가”와 “자기 사고에 흡수되었는가”의 관점에서 본다. [2][3]

`pkm` 적용:
- `daily/`는 fleeting capture 역할.
- 읽은 책, 글, 논문은 source 중심 literature note를 만든다.
- 여러 source와 경험에서 누적되는 개념은 concept 중심 permanent note를 만든다.
- 두 노트의 관계는 1:1이 아닐 수 있다. 여러 literature note가 하나의 permanent note로 모일 수 있다. [2]

### 4. Link every promoted note on purpose
원문이 가장 강조하는 부분은 연결이다. 새 노트는 기존 노트와 어떤 관계인지 질문하면서 링크해야 한다. 예시 질문도 제시한다: 가치가 있는가, 무엇과 대비되는가, 무엇을 더 발전시키는가, 나중에 어떤 맥락에서 찾을까, 반례는 무엇인가. [1]

Matuschak 자료는 태그보다 명시적 링크와 라벨 있는 관계를 권하고, Zettelkasten Method는 카테고리 선설계를 반대한다. [4][8][10]

`pkm` 적용:
- 새 노트를 만든 뒤 반드시 `pkm note links`, `pkm note show`, `pkm note orphans`로 연결 여부를 확인한다.
- 링크를 “관련 있음” 수준으로 끝내지 말고 본문에 한 줄 맥락을 남긴다.
- 태그는 진입점으로만 쓰고, 실제 사고 경로는 wikilink로 남긴다.

### 5. Prefer concept notes over project or source buckets
Tae Kim의 글은 카테고리/날짜 분류만으로는 아이디어가 갇힌다고 본다. Matuschak은 author/book/project 중심 노트보다 concept 중심 노트가 축적과 재사용을 만든다고 명시한다. [1][6]

`pkm` 적용:
- `notes/`는 계속 플랫 구조를 유지한다.
- 주제 분류는 폴더가 아니라 태그와 링크로 한다.
- 프로젝트별 장문 노트보다, 재사용 가능한 개념 노트를 먼저 만든다.

### 6. Build structure notes when clusters emerge
원문 부록 C는 여러 노트가 큰 아이디어로 묶일 때 구조 노트(overview note)를 만들라고 권한다. Zettelkasten Method도 content note 위에 structure note 층이 자연스럽게 생긴다고 설명한다. [1][4]

`pkm` 적용:
- 특정 주제에서 노트 4-7개가 자주 함께 등장하면 구조 노트 후보로 본다.
- 구조 노트에는 링크 목록만 두지 말고, 각 링크가 왜 들어가는지 한 줄 설명을 붙인다.
- 구조 노트는 태그 인덱스와 다르다. 태그 인덱스는 입구이고, 구조 노트는 작성된 관점이다. [4][10]

### 7. Write from structure, not from scratch
Tae Kim의 3단계는 “노트가 충분히 쌓이면 긴 글로 쓴다”다. 이미 각 노트가 독립적으로 이해 가능하고 연결되어 있으므로, 집필은 무에서 유를 만드는 작업이 아니라 구조화와 다듬기다. [1]

`pkm` 적용:
- 글쓰기 전에 관련 permanent note를 모은 structure note를 만든다.
- 구조 노트 순서대로 초안을 뽑는다.
- 글쓰기 중 생긴 새 생각은 다시 permanent note로 환원한다.

### 8. Keep notes editable, not sacred
Zettelkasten Method 자료는 permanent note를 “영원히 고정된 노트”가 아니라 “계속 유용한 노트”로 보라고 조언한다. [2]

`pkm` 적용:
- 기존 노트를 덧붙이고 다시 쓰는 것을 정상 루프로 본다.
- 오래된 노트도 재링크와 재서술 대상이다.
- stale note는 방치 리스트가 아니라 재점화 후보로 본다.

## Claims Table

| Claim | Evidence | PKM implication |
|---|---|---|
| 제텔카스텐의 핵심 루프는 캡처보다 연결이다 | Tae Kim의 3단계와 연결 질문, Matuschak의 dense links 원칙 [1][8] | `note show`, `note links`, `note orphans`를 승격 직후 기본 루틴으로 묶어야 한다 |
| 분류보다 개념 노트가 재사용성을 높인다 | Tae Kim의 카테고리 비판, Zettelkasten Method의 no categories, Matuschak의 concept-oriented notes [1][5][6] | `notes/` 플랫 유지, 폴더 확장보다 concept title과 wikilink 우선 |
| 태그는 보조 수단이고 링크가 핵심이다 | PKM 원칙, Matuschak의 tag 비판 [8][10] | 태그는 입구, 관계는 본문 링크와 문맥 문장으로 남긴다 |
| 구조 노트는 집필과 탐색의 상위 레이어다 | Tae Kim의 overview note, Zettelkasten Method의 structural layers [1][4] | tag note와 별도로 authored structure note가 필요하다 |
| permanent note는 고정본이 아니라 진화하는 자산이다 | Zettelkasten Method의 malleable notes [2] | stale/orphan 탐색은 청소가 아니라 리팩터링 루프다 |

## Gap Analysis: Current PKM vs Desired Zettelkasten Loop

### Already present in PKM
- 데일리 기반 캡처 진입점 (`pkm daily`, `pkm daily add`)  
- 원자 노트 생성 (`pkm note add`)  
- 백링크/고아 노트 점검 (`pkm note links`, `pkm note orphans`)  
- 태그 인덱스와 검색 (`pkm tags`, `pkm search`)  
- 데일리 승격 워크플로우 (`distill-daily`)  

### Weak or undocumented
- literature note와 permanent note의 역할 분리
- 승격 직후 연결 질문 루프
- 구조 노트 생성 기준
- 구조 노트에서 글로 이어지는 루프
- 링크에 맥락 문장을 붙이는 관행

### Not recommended
- `notes/` 안에 주제별 폴더 확장
- 태그만으로 관련성 설명하기
- source note 하나를 그대로 permanent note로 취급하는 습관
- “완벽한 permanent note”를 만들 때까지 승격 미루기

## Recommended PKM Workflow

### Loop
1. Capture
2. Distill
3. Connect
4. Structure
5. Write
6. Revisit

### Step detail
1. Capture
   데일리에 배움, 관찰, 인용 후보를 한 줄씩 남긴다. 하루에 남길 가치가 있는 것만 고른다. [1]
2. Distill
   하루 말미 혹은 다음날, 데일리 항목을 literature note 또는 permanent note로 재작성한다. 출처가 있으면 source 중심, 없으면 concept 중심으로 쓴다. [1][2][3]
3. Connect
   새 노트마다 최소 1개 이상의 기존 노트에 링크한다. 아래 질문 중 최소 2개에 답하며 링크를 건다. [1][8]
4. Structure
   연결이 4개 이상 모인 주제는 structure note를 만든다. 노트 목록이 아니라 “왜 이 노트들이 함께 읽혀야 하는가”를 드러낸다. [1][4][10]
5. Write
   structure note를 기반으로 초안을 만든다. 초안에서 새로 생긴 주장이나 요약은 다시 permanent note로 환원한다. [1]
6. Revisit
   orphan/stale note를 주기적으로 재검토하고, 오래된 노트를 새 구조에 재편입한다. [2][8]

## Link Prompt Set for PKM
새 note를 만들고 나면 아래 질문으로 링크를 강제한다. 원문 질문을 `pkm`에 맞게 약간 정제했다. [1]

- 이 노트는 무엇을 설명하거나 반박하는가?
- 어떤 기존 노트를 더 구체화하거나 일반화하는가?
- 반례가 되는 노트는 무엇인가?
- 내가 나중에 어떤 검색어 혹은 상황에서 이 노트를 찾을까?
- 이 노트가 source라면, 여기서 살아남아 permanent note가 될 개념은 무엇인가?

## Naming and Note Shape Guidance
- 제목은 완전한 문장 혹은 최소한 명확한 주장형 구를 우선한다. [7][9]
- note 하나는 하나의 개념만 다룬다. [8]
- 본문 첫 문단에서 왜 중요한지 적는다.
- 본문 말미에는 `관련:` 블록으로 source, neighbor, structure note를 연결한다.
- 태그는 1-3개 정도의 진입점만 부여한다.

## Concrete PKM Mapping

| Zettelkasten move | PKM command or artifact |
|---|---|
| fleeting capture | `pkm daily add`, `pkm daily todo` |
| literature/permanent note creation | `pkm note add`, direct file editing |
| duplicate check before promotion | `pkm search`, `pkm note show` |
| backlink inspection | `pkm note links`, `pkm note show` |
| orphan repair | `pkm note orphans` |
| structure discovery | `pkm tags show`, `pkm search`, authored structure note |
| periodic refinement | `pkm note stale --days 30` |
| daily-to-note promotion | existing `distill-daily` workflow |

## Proposed Operating Cadence
- 즉시: 떠오른 생각은 데일리에 한 줄 캡처
- 일일 1회: 캡처를 note로 승격하고 최소 1개 링크 추가
- 주 2회: orphan/stale 점검
- 주 1회: 구조 노트 갱신
- 월 1회: 구조 노트에서 글감 후보 선정

## Counterevidence and Cautions
- 태그를 완전히 버릴 필요는 없다. 작은 vault에서는 여전히 좋은 입구다. 다만 사고의 핵심 연결 구조를 태그에 맡기면 신호가 약해진다. [4][10]
- literature/permanent 구분은 절대적 형식 규칙이 아니다. 중요한 것은 “미래에 다시 쓸 수 있는 형태”로 살아남는지다. [2][3]
- structure note는 중앙집권 목차가 아니라, 관심사가 자라며 생기는 관점별 지도다. 미리 전체 체계를 설계하려 들면 오히려 제텔카스텐의 장점이 줄어든다. [4][5]

## Recommended Repo Artifacts
- `docs/zettelkasten-pkm-research-20260406.md`
- `skill/workflows/zettelkasten-loop.md`
- `skill/commands/pkm/zettelkasten-loop.md`

## Final Recommendation
`pkm`은 이미 제텔카스텐 앱으로서 부족하지 않다. 부족한 것은 기능보다 루프의 명시성이다. 가장 큰 개선점은 세 가지다:

1. 데일리 캡처를 literature/permanent 승격으로 명확히 분기할 것
2. 승격 직후 “연결 질문”을 사용해 수동 링크를 강제할 것
3. 구조 노트를 별도 산출물로 인정하고 거기서 글쓰기를 시작할 것

이 세 가지만 문서화해도 `pkm`은 “마크다운 노트 CLI”에서 “제텔카스텐 운영 체계”로 한 단계 올라간다.

## Sources
1. Tae Kim, "제텔카스텐: 하루 메모 6장으로 혁신적인 아이디어를 만드는 방법". https://tkim.co/2020/09/zettelkasten/
2. Zettelkasten Method, "All notes are malleable: Strive for permanently useful notes, not permanently unchanging notes". https://zettelkasten.de/posts/literature-notes-vs-permanent-notes/
3. Zettelkasten Method, "From Fleeting Notes to Project Notes – Concepts of 'How to Take Smart Notes' by Sönke Ahrens". https://zettelkasten.de/posts/concepts-sohnke-ahrens-explained/
4. Zettelkasten Method, "A Tale of Complexity – Structural Layers in Note Taking". https://zettelkasten.de/posts/three-layers-structure-zettelkasten/
5. Zettelkasten Method, "Why Categories for Your Note Archive are a Bad Idea". https://zettelkasten.de/posts/no-categories/
6. Andy Matuschak, "Evergreen notes should be concept-oriented". https://notes.andymatuschak.org/z2hQEhqWkdRLL9JUwfawZZx
7. Andy Matuschak, "Evergreen note titles are like APIs". https://notes.andymatuschak.org/Evergreen_note_titles_are_like_APIs
8. Andy Matuschak, "Evergreen notes should be densely linked". https://notes.andymatuschak.org/Evergreen_notes_should_be_densely_linked
9. Andy Matuschak, "Prefer note titles with complete phrases to sharpen claims". https://notes.andymatuschak.org/About_these_notes?stackedNotes=z3KmNj3oKKSTJfqdfSEBzTQiCVGoC4GfK3rYW&stackedNotes=z4SDCZQeRo4xFEQ8H4qrSqd68ucpgE6LU155C&stackedNotes=z6bci25mVUBNFdVWSrQNKr6u7AZ1jFzfTVbMF
10. Andy Matuschak, "Tags are an ineffective association structure". https://notes.andymatuschak.org/Tags_are_an_ineffective_association_structure
