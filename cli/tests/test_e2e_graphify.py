"""E2E tests for the graphify feature set.

These tests build real vaults with sentence-transformers embeddings.
Each test does actual embedding work — expect ~5-15s per test.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from pkm.config import VaultConfig
from pkm.search_engine import build_index


def _run(coro):
    """Run an async tool coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: tmp_vault with clear topic clusters
# ---------------------------------------------------------------------------

NOTE_CONTENTS = {
    # Python / ML cluster (3 notes)
    "python-basics": (
        "---\nid: python-basics\ntags:\n  - python\n  - programming\n---\n\n"
        "Python is a high-level programming language known for its simplicity and readability. "
        "It supports multiple programming paradigms including procedural, object-oriented, and "
        "functional programming. Python's extensive standard library and rich ecosystem of "
        "third-party packages make it ideal for data science, machine learning, and web development.\n"
    ),
    "machine-learning": (
        "---\nid: machine-learning\ntags:\n  - ml\n  - python\n  - ai\n---\n\n"
        "Machine learning is a subset of artificial intelligence that enables systems to learn "
        "from data without being explicitly programmed. Key algorithms include linear regression, "
        "decision trees, random forests, neural networks, and support vector machines. "
        "Python libraries like scikit-learn, TensorFlow, and PyTorch are widely used.\n"
    ),
    "neural-networks": (
        "---\nid: neural-networks\ntags:\n  - ml\n  - deep-learning\n  - ai\n---\n\n"
        "Neural networks are computational models inspired by the human brain. They consist of "
        "layers of interconnected nodes (neurons) that process information. Deep learning uses "
        "multiple hidden layers to learn hierarchical representations. Convolutional networks "
        "excel at image recognition while recurrent networks handle sequential data.\n"
    ),
    # Cooking cluster (3 notes)
    "italian-pasta": (
        "---\nid: italian-pasta\ntags:\n  - cooking\n  - italian\n  - food\n---\n\n"
        "Italian pasta is a staple food made from durum wheat semolina and water. Classic pasta "
        "shapes include spaghetti, penne, rigatoni, and tagliatelle. Traditional sauces such as "
        "carbonara, bolognese, and amatriciana each have regional origins in Italy. Al dente "
        "cooking means pasta retains a slight bite and firmness.\n"
    ),
    "french-cuisine": (
        "---\nid: french-cuisine\ntags:\n  - cooking\n  - french\n  - food\n---\n\n"
        "French cuisine is renowned worldwide for its sophistication and technique. Classic "
        "preparations include consommé, beurre blanc, and hollandaise sauce. French cooking "
        "emphasizes fresh ingredients, proper knife skills, and mother sauces. Dishes like "
        "coq au vin, bouillabaisse, and ratatouille reflect regional French culinary traditions.\n"
    ),
    "baking-bread": (
        "---\nid: baking-bread\ntags:\n  - cooking\n  - baking\n  - food\n---\n\n"
        "Bread baking is both science and art. Yeast fermentation produces carbon dioxide that "
        "makes dough rise, while gluten development gives bread its chewy texture. Sourdough "
        "uses wild yeast starter for complex flavors. Key variables include hydration ratio, "
        "fermentation time, and oven temperature for achieving perfect crust and crumb.\n"
    ),
}

# Bridge note: mentions both ML and cooking (for surprising connections test)
BRIDGE_NOTE = {
    "data-driven-recipes": (
        "---\nid: data-driven-recipes\ntags:\n  - ml\n  - cooking\n  - data-science\n---\n\n"
        "Machine learning algorithms can optimize recipes and predict ingredient combinations. "
        "Neural networks trained on flavor compound databases can suggest novel pairings. "
        "This intersection of data science and culinary arts uses Python to analyze thousands "
        "of recipes, clustering flavor profiles and recommending ingredient substitutions "
        "similar to how recommendation systems work in artificial intelligence.\n"
    ),
}


@pytest.fixture
def tmp_vault(tmp_path: Path) -> VaultConfig:
    """Create a tmp vault with 6 topic-clustered notes + 1 bridge note."""
    vault_path = tmp_path / "e2e-vault"
    for d in ("notes", "daily", "tags", ".pkm"):
        (vault_path / d).mkdir(parents=True)

    all_notes = {**NOTE_CONTENTS, **BRIDGE_NOTE}
    for note_id, content in all_notes.items():
        (vault_path / "notes" / f"{note_id}.md").write_text(content, encoding="utf-8")

    return VaultConfig(name="e2e-vault", path=vault_path)


# ---------------------------------------------------------------------------
# Scenario 1: build_index creates graph.json and graph_enriched.json
# ---------------------------------------------------------------------------


def test_e2e_pkm_index_creates_enriched_graph(tmp_vault: VaultConfig) -> None:
    """build_index produces both graph.json and graph_enriched.json with clusters."""
    build_index(tmp_vault)

    assert (tmp_vault.pkm_dir / "graph.json").exists(), "graph.json not created"
    assert tmp_vault.graph_enriched_path.exists(), "graph_enriched.json not created"

    data = json.loads(tmp_vault.graph_enriched_path.read_text())
    assert "clusters" in data
    clusters = data["clusters"]
    assert len(clusters) >= 1

    # Every cluster has centroid and is_new=True on first run
    for c in clusters:
        assert "centroid" in c
        assert c["is_new"] is True


# ---------------------------------------------------------------------------
# Scenario 2: second run detects is_new=False with small centroid_drift
# ---------------------------------------------------------------------------


def test_e2e_second_index_run_detects_drift(tmp_vault: VaultConfig) -> None:
    """Running build_index twice on unchanged vault gives is_new=False, drift ≈ 0."""
    build_index(tmp_vault)
    build_index(tmp_vault)

    data = json.loads(tmp_vault.graph_enriched_path.read_text())
    clusters = data["clusters"]
    assert len(clusters) >= 1

    for c in clusters:
        assert c["is_new"] is False, (
            f"Cluster {c['id']} still marked is_new on second run"
        )
        assert c["centroid_drift"] is not None
        assert c["centroid_drift"] < 0.01, (
            f"Cluster {c['id']} drift={c['centroid_drift']:.4f} unexpectedly large on unchanged vault"
        )


# ---------------------------------------------------------------------------
# Scenario 3: find_surprising_connections returns bridge note at top
# ---------------------------------------------------------------------------


def test_e2e_find_surprising_connections_returns_bridge_notes(
    tmp_vault: VaultConfig,
) -> None:
    """Bridge note bridging ML and Cooking clusters should appear in results."""
    build_index(tmp_vault)

    from pkm.graph import find_surprising_connections

    results = find_surprising_connections(tmp_vault, top_n=5)
    assert len(results) > 0, "Expected non-empty surprising connections"

    [r["title"] for r in results]
    # The bridge note title comes from frontmatter (id used as stem, title defaults to id)
    note_ids = [r["note_id"] for r in results]
    assert "data-driven-recipes" in note_ids, (
        f"Bridge note 'data-driven-recipes' not in top results: {note_ids}"
    )

    # Bridge note should be in top-3
    bridge_rank = next(
        i for i, r in enumerate(results) if r["note_id"] == "data-driven-recipes"
    )
    assert bridge_rank < 3, f"Bridge note ranked {bridge_rank}, expected top-3"


# ---------------------------------------------------------------------------
# Scenario 4: CLI JSON output via CliRunner
# ---------------------------------------------------------------------------


def test_e2e_pkm_graph_surprising_cli_json(tmp_vault: VaultConfig) -> None:
    """pkm graph surprising outputs valid JSON with 'results' key by default."""
    build_index(tmp_vault)

    from click.testing import CliRunner
    from pkm.cli import main

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--vault", tmp_vault.name, "graph", "surprising"],
        obj={"vault": tmp_vault},
        catch_exceptions=False,
    )

    assert result.exit_code == 0, f"CLI failed: {result.output}"
    # Strip any non-JSON prefix lines (e.g. version update banner)
    output = result.output
    json_start = output.find("{")
    assert json_start >= 0, f"No JSON found in output: {output}"
    payload = json.loads(output[json_start:])
    assert "results" in payload


# ---------------------------------------------------------------------------
# Scenario 5: add_wikilink creates ## Related section when absent
# ---------------------------------------------------------------------------


def test_e2e_add_wikilink_creates_related_section(tmp_vault: VaultConfig) -> None:
    """add_wikilink creates '## Related' at EOF when note has none."""
    from pkm.tools.links import add_wikilink

    # python-basics has no ## Related section
    os.environ["PKM_VAULT_DIR"] = str(tmp_vault.path)
    try:
        result = _run(
            add_wikilink(
                source_note_id="python-basics",
                target_note_id="machine-learning",
                description="both cover Python ML ecosystem",
            )
        )
        assert "Error" not in result, f"Unexpected error: {result}"

        text = (tmp_vault.notes_dir / "python-basics.md").read_text(encoding="utf-8")
        assert "## Related" in text
        assert "- [[machine-learning|both cover Python ML ecosystem]]" in text
        # Section must appear at end-of-file area
        related_pos = text.index("## Related")
        assert related_pos > text.index("---\n\n"), "## Related not in body"
    finally:
        del os.environ["PKM_VAULT_DIR"]


# ---------------------------------------------------------------------------
# Scenario 6: add_wikilink appends to existing ## Related section
# ---------------------------------------------------------------------------


def test_e2e_add_wikilink_appends_to_existing_related(tmp_vault: VaultConfig) -> None:
    """add_wikilink adds new entry while preserving existing ## Related entries."""
    # First add one entry
    note_path = tmp_vault.notes_dir / "python-basics.md"
    original = note_path.read_text(encoding="utf-8")
    note_path.write_text(
        original.rstrip("\n")
        + "\n\n## Related\n\n- [[neural-networks|deep learning basics]]\n",
        encoding="utf-8",
    )

    from pkm.tools.links import add_wikilink

    os.environ["PKM_VAULT_DIR"] = str(tmp_vault.path)
    try:
        result = _run(
            add_wikilink(
                source_note_id="python-basics",
                target_note_id="machine-learning",
                description="both cover Python ML",
            )
        )
        assert "Error" not in result, f"Unexpected error: {result}"

        text = note_path.read_text(encoding="utf-8")
        assert "- [[neural-networks|deep learning basics]]" in text, (
            "Existing entry removed"
        )
        assert "- [[machine-learning|both cover Python ML]]" in text, (
            "New entry not added"
        )

        text.index("## Related")
        assert text.count("## Related") == 1, "Duplicate ## Related sections created"
    finally:
        del os.environ["PKM_VAULT_DIR"]


# ---------------------------------------------------------------------------
# Scenario 7: create_hub_note writes correct frontmatter and ## Members
# ---------------------------------------------------------------------------


def test_e2e_create_hub_note_writes_frontmatter_and_members(
    tmp_vault: VaultConfig,
) -> None:
    """create_hub_note produces a note with type: index, importance: 6, ## Members."""
    build_index(tmp_vault)

    data = json.loads(tmp_vault.graph_enriched_path.read_text())
    clusters = data["clusters"]
    assert len(clusters) >= 1

    cluster_id = clusters[0]["id"]

    from pkm.tools.search import create_hub_note

    os.environ["PKM_VAULT_DIR"] = str(tmp_vault.path)
    try:
        result = _run(
            create_hub_note(
                cluster_index=cluster_id,
                title="Test Hub Note",
                description="This is a test hub note for cluster 0.",
            )
        )
        assert "Error" not in result, f"Unexpected error: {result}"
        assert "Test Hub Note" in result

        # Find created file
        list(tmp_vault.notes_dir.glob("*test-hub*")) + list(
            tmp_vault.notes_dir.glob("*Test-Hub*")
        )
        # Also search by any file created after we started
        created_files = [
            f
            for f in tmp_vault.notes_dir.glob("*.md")
            if "test" in f.stem.lower() or "hub" in f.stem.lower()
        ]
        assert len(created_files) >= 1, (
            f"Hub note file not found; files: {list(tmp_vault.notes_dir.glob('*.md'))}"
        )

        hub_path = created_files[0]
        text = hub_path.read_text(encoding="utf-8")

        assert "type: index" in text
        assert "importance: 6" in text
        assert "## Members" in text

        # Each member should appear as a wikilink
        members = clusters[0].get("members", [])
        for member in members:
            assert f"[[{member}]]" in text, f"Member [[{member}]] missing from hub note"
    finally:
        del os.environ["PKM_VAULT_DIR"]


# ---------------------------------------------------------------------------
# Scenario 8: list_clusters matches hub note by centroid
# ---------------------------------------------------------------------------


def test_e2e_list_clusters_matches_hub_note_by_centroid(
    tmp_vault: VaultConfig,
) -> None:
    """After creating a type:index hub note and re-indexing, list_clusters matches it."""
    # Step 1: build index to discover clusters
    build_index(tmp_vault)

    data = json.loads(tmp_vault.graph_enriched_path.read_text())
    clusters = data["clusters"]
    assert len(clusters) >= 1

    # Step 2: create hub note via create_hub_note (real round-trip, no workarounds).
    # Find the ML/Python-themed cluster to ensure the hub embeds close to its centroid.
    from pkm.tools.search import create_hub_note

    os.environ["PKM_VAULT_DIR"] = str(tmp_vault.path)
    try:
        ml_cluster = next(
            (
                c
                for c in clusters
                if any(t in c.get("top_tags", []) for t in ("ml", "python", "ai"))
            ),
            clusters[0],
        )
        hub_result = _run(
            create_hub_note(
                cluster_index=ml_cluster["id"],
                title="ML and Python Index",
                description=(
                    "Index for machine learning, Python programming, neural networks, deep learning, "
                    "artificial intelligence, scikit-learn, TensorFlow, PyTorch, data science, and "
                    "Python libraries for ML. Entry point for all Python-based machine learning notes."
                ),
            )
        )
        assert "Error" not in hub_result, f"create_hub_note failed: {hub_result}"
    finally:
        del os.environ["PKM_VAULT_DIR"]

    # Step 3: re-index so hub note gets embedded
    build_index(tmp_vault)

    # Step 4: call list_clusters and verify hub matching
    from pkm.tools.search import list_clusters

    os.environ["PKM_VAULT_DIR"] = str(tmp_vault.path)
    try:
        output = _run(list_clusters())
        assert output.startswith("{"), f"Expected JSON output, got: {output[:100]}"

        payload = json.loads(output)
        assert "clusters" in payload

        matched = [c for c in payload["clusters"] if c.get("hub_note") is not None]
        assert len(matched) >= 1, (
            f"No cluster matched a hub note. clusters={payload['clusters']}"
        )
        hub_titles = [c["hub_note"] for c in matched]
        assert any("ML and Python" in t for t in hub_titles), (
            f"Expected 'ML and Python' hub in hub_titles={hub_titles}"
        )
    finally:
        del os.environ["PKM_VAULT_DIR"]


# ---------------------------------------------------------------------------
# Scenario 9: graceful degradation without vector.db
# ---------------------------------------------------------------------------


def test_e2e_graceful_degradation_without_vector_db(tmp_vault: VaultConfig) -> None:
    """build_enriched_graph on vault with graph.json but no vector.db does not write enriched."""
    from pkm.graph import build_ast_and_graph, build_enriched_graph

    # Build only the structural graph (no embeddings)
    build_ast_and_graph(tmp_vault)
    assert (tmp_vault.pkm_dir / "graph.json").exists()
    assert not (tmp_vault.pkm_dir / "vector.db").exists()

    # Should return silently without writing graph_enriched.json
    build_enriched_graph(tmp_vault)
    assert not tmp_vault.graph_enriched_path.exists(), (
        "graph_enriched.json should not be written when vector.db is absent"
    )


# ---------------------------------------------------------------------------
# Scenario 10: worker.py prompt sanity check
# ---------------------------------------------------------------------------


def test_e2e_worker_prompt_mentions_new_tools() -> None:
    """worker.py handle_zettelkasten_maintenance system prompt references all graphify tools."""
    import inspect
    import pkm.worker as worker_module

    source = inspect.getsource(worker_module)

    required = [
        "find_surprising_connections",
        "list_clusters",
        "create_hub_note",
        "add_wikilink",
        "CLUSTER DRIFT REVIEW",
    ]
    for keyword in required:
        assert keyword in source, f"'{keyword}' not found in worker.py"
