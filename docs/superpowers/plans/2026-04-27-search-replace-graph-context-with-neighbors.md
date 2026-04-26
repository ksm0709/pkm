# search: graph_context → related_notes (neighbors 재사용) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pkm search --format json`의 `graph_context` 필드(raw ego_graph via daemon)를 `related_notes` 필드(구조화된 outbound/inbound/semantic via `_get_note_neighbors_data`)로 교체하고, 같은 로직을 MCP `search` 툴에도 적용해 중복 구현을 제거한다.

**Architecture:** `tools/links.py:_get_note_neighbors_data()`는 이미 daemon 없이 직접 파일을 읽어 구조화된 이웃 정보를 반환한다. `graph_context`(raw networkx node_link_data via daemon)를 이걸로 대체하면 daemon 의존성이 사라지고 출력 포맷이 더 명확해진다. `tools/search.py:get_graph_context` 툴도 `tools/links.py:get_note_neighbors`와 중복이므로 함께 제거한다.

**Tech Stack:** Python, networkx, Click CLI, FastMCP

---

## 변경 파일 목록

| 파일 | 변경 유형 | 역할 |
|------|----------|------|
| `cli/src/pkm/commands/search.py` | Modify | `--depth` 제거, `graph_context` → `related_notes` |
| `cli/src/pkm/mcp_server.py` | Modify | search 결과에 `related_notes` 추가 |
| `cli/src/pkm/tools/search.py` | Modify | `get_graph_context` 툴 제거 |
| `cli/src/pkm/search_engine.py` | Modify | `get_graph_context_via_daemon()` 제거 |
| `cli/src/pkm/daemon.py` | Modify | `get_graph_context` 액션 핸들러 제거 |
| `cli/tests/test_get_graph_context_tier.py` | Delete | 제거된 코드의 테스트 |
| `cli/tests/test_search_related_notes.py` | Create | `related_notes` 포함 테스트 |

---

## Task 1: `commands/search.py` — `graph_context` → `related_notes`

**Files:**
- Modify: `cli/src/pkm/commands/search.py:62` (JSON 직렬화)
- Modify: `cli/src/pkm/commands/search.py:173-184` (`--depth` 제거)
- Modify: `cli/src/pkm/commands/search.py:261-271` (로직 교체)

- [ ] **Step 1: 실패 테스트 작성**

`cli/tests/test_search_related_notes.py` 생성:

```python
"""Tests for related_notes field in pkm search JSON output."""
import json
import pytest
from click.testing import CliRunner
from pkm.commands.search import search_cmd


def _make_vault(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "notes").mkdir()
    pkm_dir = vault_dir / ".pkm"
    pkm_dir.mkdir()
    return vault_dir, pkm_dir


def _make_graph(pkm_dir, nodes, edges):
    import networkx as nx
    G = nx.DiGraph()
    for n, attrs in nodes.items():
        G.add_node(n, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    (pkm_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(G)), encoding="utf-8"
    )


def test_search_result_has_related_notes_field(tmp_path, monkeypatch):
    """search JSON output includes related_notes with outbound/inbound/semantic keys."""
    vault_dir, pkm_dir = _make_vault(tmp_path)
    _make_graph(
        pkm_dir,
        nodes={"note-a": {"title": "Note A"}, "note-b": {"title": "Note B"}},
        edges=[("note-a", "note-b", {"type": "wikilink"})],
    )

    from pkm.config import VaultConfig
    vault = VaultConfig(name="test", path=vault_dir)

    from pkm.models import SearchResult
    results = [
        SearchResult(note_id="note-a", title="Note A", score=0.9, rank=1, tags=[])
    ]

    from pkm.commands.search import format_search_results
    from rich.console import Console
    from io import StringIO
    import sys

    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    format_search_results(
        query="test",
        results=results,
        output_format="json",
        console=Console(),
        vault=vault,
    )
    output = json.loads(captured.getvalue())

    assert "results" in output
    r = output["results"][0]
    assert "related_notes" in r
    assert "outbound" in r["related_notes"]
    assert "inbound" in r["related_notes"]
    assert "semantic" in r["related_notes"]
    assert any(n["note_id"] == "note-b" for n in r["related_notes"]["outbound"])


def test_search_result_no_graph_context_key(tmp_path, monkeypatch):
    """related_notes replaces graph_context — old key must not appear."""
    vault_dir, pkm_dir = _make_vault(tmp_path)
    _make_graph(pkm_dir, nodes={"note-a": {"title": "Note A"}}, edges=[])

    from pkm.config import VaultConfig
    vault = VaultConfig(name="test", path=vault_dir)

    from pkm.models import SearchResult
    results = [
        SearchResult(note_id="note-a", title="Note A", score=0.9, rank=1, tags=[])
    ]

    from pkm.commands.search import format_search_results
    from rich.console import Console
    from io import StringIO
    import sys

    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    format_search_results(
        query="test",
        results=results,
        output_format="json",
        console=Console(),
        vault=vault,
    )
    output = json.loads(captured.getvalue())
    r = output["results"][0]
    assert "graph_context" not in r


def test_search_no_depth_option(tmp_path):
    """--depth option must not exist on search command."""
    runner = CliRunner()
    result = runner.invoke(search_cmd, ["--help"])
    assert "--depth" not in result.output
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /home/taeho/repos/pkm/cli
python -m pytest tests/test_search_related_notes.py -v 2>&1 | tail -20
```

Expected: FAIL (3 failures — `related_notes` 없고 `graph_context` 있고 `--depth` 있음)

- [ ] **Step 3: `format_search_results` JSON 키 변경 (`graph_context` → `related_notes`)**

`cli/src/pkm/commands/search.py:62`:

```python
# 변경 전
"graph_context": getattr(r, "graph_context", None),
# 변경 후
"related_notes": getattr(r, "related_notes", None),
```

- [ ] **Step 4: `--depth` 옵션 제거 및 로직 교체**

`cli/src/pkm/commands/search.py:173-184` 에서 `--depth` 옵션 라인 제거:
```python
# 아래 줄 삭제
@click.option("--depth", type=int, default=1, help="Graph traversal depth")
```

`search_cmd` 함수 시그니처에서 `depth: int` 파라미터 제거.

`cli/src/pkm/commands/search.py:261-271` 블록을 교체:

```python
# Append graph neighbors as related_notes
if output_format == "json":
    from pkm.tools.links import _get_note_neighbors_data

    for r in results:
        try:
            r.related_notes = _get_note_neighbors_data(
                vault, r.note_id, include_semantic=True
            )
        except Exception:
            pass
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd /home/taeho/repos/pkm/cli
python -m pytest tests/test_search_related_notes.py -v
```

Expected: PASS (3/3)

- [ ] **Step 6: 전체 테스트 이상 없음 확인**

```bash
cd /home/taeho/repos/pkm/cli
python -m pytest --tb=short -q 2>&1 | tail -15
```

Expected: 기존 테스트 수 이상 없음 (test_get_graph_context_tier.py 제외한 전체 통과)

- [ ] **Step 7: 커밋**

```bash
git add cli/src/pkm/commands/search.py cli/tests/test_search_related_notes.py
git commit -m "feat(search): replace graph_context with related_notes via _get_note_neighbors_data"
```

---

## Task 2: `mcp_server.py` — search 결과에 `related_notes` 추가

**Files:**
- Modify: `cli/src/pkm/mcp_server.py:190-204` (search 툴 결과 포맷)

- [ ] **Step 1: 실패 테스트 작성**

`cli/tests/test_search_related_notes.py`에 추가:

```python
def test_mcp_search_has_related_notes(tmp_path, monkeypatch):
    """MCP search tool includes related_notes in each result."""
    vault_dir, pkm_dir = _make_vault(tmp_path)
    _make_graph(
        pkm_dir,
        nodes={"note-a": {"title": "Note A"}, "note-b": {"title": "Note B"}},
        edges=[("note-a", "note-b", {"type": "wikilink"})],
    )

    from pkm.config import VaultConfig
    vault = VaultConfig(name="test", path=vault_dir)

    from pkm.models import SearchResult
    mock_results = [
        SearchResult(note_id="note-a", title="Note A", score=0.9, rank=1, tags=[])
    ]

    import pkm.mcp_server as mcp_mod
    monkeypatch.setattr(mcp_mod, "_get_vault", lambda v=None: vault)

    from pkm import search_engine
    monkeypatch.setattr(search_engine, "search_via_daemon", lambda *a, **kw: mock_results)

    result = mcp_mod.search(query="test")
    assert "results" in result
    r = result["results"][0]
    assert "related_notes" in r
    assert "outbound" in r["related_notes"]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /home/taeho/repos/pkm/cli
python -m pytest tests/test_search_related_notes.py::test_mcp_search_has_related_notes -v
```

Expected: FAIL

- [ ] **Step 3: MCP search 툴에 `related_notes` 추가**

`cli/src/pkm/mcp_server.py` search 함수의 결과 포맷 수정:

```python
        from pkm.tools.links import _get_note_neighbors_data

        def _related(r):
            try:
                return _get_note_neighbors_data(
                    target_vault, r.note_id, include_semantic=True
                )
            except Exception:
                return None

        return {
            "results": [
                {
                    "note_id": r.note_id,
                    "title": r.title,
                    "score": round(r.score, 4),
                    "tags": r.tags,
                    "memory_type": r.memory_type,
                    "importance": r.importance,
                    "path": r.path,
                    "rank": r.rank,
                    "related_notes": _related(r),
                }
                for r in results
            ],
            "count": len(results),
        }
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd /home/taeho/repos/pkm/cli
python -m pytest tests/test_search_related_notes.py -v
```

Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add cli/src/pkm/mcp_server.py cli/tests/test_search_related_notes.py
git commit -m "feat(mcp): add related_notes to search tool output"
```

---

## Task 3: 중복 코드 제거 — `get_graph_context` 툴, `get_graph_context_via_daemon`, daemon 핸들러

**Files:**
- Modify: `cli/src/pkm/tools/search.py` — `get_graph_context` 함수 + import 제거
- Modify: `cli/src/pkm/search_engine.py` — `get_graph_context_via_daemon()` 제거
- Modify: `cli/src/pkm/daemon.py` — `get_graph_context` 액션 핸들러 제거
- Delete: `cli/tests/test_get_graph_context_tier.py`

- [ ] **Step 1: `tools/search.py`에서 `get_graph_context` 제거**

`cli/src/pkm/tools/search.py`:
- `from pkm.search_engine import get_graph_context_via_daemon` 임포트 라인 삭제
- `@tool() def get_graph_context(...)` 함수 전체 삭제 (라인 89-112)

- [ ] **Step 2: `search_engine.py`에서 `get_graph_context_via_daemon` 제거**

`cli/src/pkm/search_engine.py:556-595`:
- `def get_graph_context_via_daemon(...)` 함수 전체 삭제

- [ ] **Step 3: `daemon.py`에서 `get_graph_context` 핸들러 제거**

`cli/src/pkm/daemon.py:385-424`:
- `elif action == "get_graph_context":` 블록 전체 삭제 (라인 385~424, 마지막 `writer.write(res_data.encode("utf-8"))` 포함)

- [ ] **Step 4: `test_get_graph_context_tier.py` 삭제**

```bash
rm /home/taeho/repos/pkm/cli/tests/test_get_graph_context_tier.py
```

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
cd /home/taeho/repos/pkm/cli
python -m pytest --tb=short -q 2>&1 | tail -15
```

Expected: 이전 테스트 수 − (test_get_graph_context_tier.py 테스트 수) = 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add cli/src/pkm/tools/search.py cli/src/pkm/search_engine.py cli/src/pkm/daemon.py
git rm cli/tests/test_get_graph_context_tier.py
git commit -m "refactor: remove get_graph_context_via_daemon and daemon handler (replaced by _get_note_neighbors_data)"
```

---

## Self-Review

**Spec coverage:**
- [x] `pkm search --format json` → `related_notes` 포함, `graph_context` 제거
- [x] `mcp search` → `related_notes` 포함
- [x] `--depth` 옵션 제거 (neighbors는 항상 1-hop)
- [x] `get_graph_context` 툴/함수/핸들러 제거
- [x] `test_get_graph_context_tier.py` 삭제

**Placeholder 점검:** 없음 — 모든 코드 블록 완전함.

**타입 일관성:** `_get_note_neighbors_data()` 반환값 `dict[note_id, outbound, inbound, semantic]`이 Task 1, 2 모두에서 동일하게 사용됨.

**주의사항:**
- `_get_note_neighbors_data`는 `graph.json` 없을 때 `FileNotFoundError` raise. 두 곳 모두 `try/except Exception: pass`로 graceful degradation 처리.
- `format_search_results`에 `vault` 파라미터가 이미 있는지 확인 필요. 없다면 Task 1 Step 4에서 추가.
