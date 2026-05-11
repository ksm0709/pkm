from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


def test_force_included_static_assets_exist_for_source_archive_builds() -> None:
    """GitHub source archives must contain hatchling force-include sources."""
    cli_root = Path(__file__).resolve().parents[1]
    pyproject = cli_root / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    force_include = (
        config.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("force-include", {})
    )

    assert force_include, "wheel force-include entries should remain explicit"
    for source in force_include:
        source_path = cli_root / source
        assert source_path.exists(), f"Missing force-include source: {source}"


def test_bundled_web_static_entrypoint_is_tracked_in_source_tree() -> None:
    static_dir = Path(__file__).resolve().parents[1] / "src" / "pkm" / "web" / "static"

    assert (static_dir / "index.html").is_file()
    assert (static_dir / "_app" / "version.json").is_file()
