"""Wikilink extraction and resolution for PKM vaults."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pkm.config import VaultConfig

# Skip ![[embeds]] — use negative lookbehind for !
# Match [[target]] and [[target|alias]] — capture only target
_LINK_PATTERN = re.compile(r"(?<!\!)\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
_LINK_REWRITE_PATTERN = re.compile(r"(?<!\!)\[\[([^\]|]+?)(\|[^\]]+?)?\]\]")
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)


@dataclass(frozen=True)
class WikilinkRewriteResult:
    changed_files: int
    replacements: int
    paths: list[str]


def extract_links(text: str) -> list[str]:
    """Extract all wikilink targets from text, deduped, code blocks excluded."""
    text = _CODE_BLOCK.sub("", text)

    def _clean_target(target: str) -> str:
        target = target.strip()
        return target[:-3] if target.endswith(".md") else target

    targets = [_clean_target(m.group(1)) for m in _LINK_PATTERN.finditer(text)]
    return list(dict.fromkeys(targets))


def normalize_wikilink_target(target: str) -> str:
    """Normalize wikilink targets for matching while preserving stored IDs."""
    target = target.strip()
    return target[:-3] if target.endswith(".md") else target


def _rewrite_wikilinks_segment(text: str, old_target: str, new_target: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        target = match.group(1).strip()
        alias = match.group(2) or ""
        if normalize_wikilink_target(target) != old_target:
            return match.group(0)
        count += 1
        return f"[[{new_target}{alias}]]"

    return _LINK_REWRITE_PATTERN.sub(replace, text), count


def rewrite_wikilink_targets(
    text: str,
    old_target: str,
    new_target: str,
) -> tuple[str, int]:
    """Rewrite wikilinks to a renamed/moved note, preserving aliases.

    Fenced code blocks and embeds are intentionally ignored so examples and
    embedded assets are not silently rewritten.
    """
    old_target = normalize_wikilink_target(old_target)
    new_target = normalize_wikilink_target(new_target)
    if not old_target or not new_target or old_target == new_target:
        return text, 0

    parts: list[str] = []
    count = 0
    cursor = 0
    for match in _CODE_BLOCK.finditer(text):
        rewritten, n = _rewrite_wikilinks_segment(
            text[cursor : match.start()], old_target, new_target
        )
        parts.append(rewritten)
        parts.append(match.group(0))
        count += n
        cursor = match.end()
    rewritten, n = _rewrite_wikilinks_segment(text[cursor:], old_target, new_target)
    parts.append(rewritten)
    count += n
    return "".join(parts), count


def iter_markdown_files(vault: VaultConfig, *, include_tags: bool = True) -> list[Path]:
    dirs = [vault.notes_dir, vault.daily_dir]
    if include_tags:
        dirs.append(vault.tags_dir)
    return [
        md_file
        for directory in dirs
        if directory.is_dir()
        for md_file in sorted(directory.rglob("*.md"))
    ]


def rewrite_wikilinks_in_vault(
    vault: VaultConfig,
    old_target: str,
    new_target: str,
    *,
    include_tags: bool = True,
) -> WikilinkRewriteResult:
    """Rewrite all vault wikilinks from old_target to new_target."""
    changed_paths: list[str] = []
    replacements = 0
    for md_file in iter_markdown_files(vault, include_tags=include_tags):
        text = md_file.read_text(encoding="utf-8")
        rewritten, count = rewrite_wikilink_targets(text, old_target, new_target)
        if count:
            md_file.write_text(rewritten, encoding="utf-8")
            changed_paths.append(str(md_file))
            replacements += count
    return WikilinkRewriteResult(
        changed_files=len(changed_paths),
        replacements=replacements,
        paths=changed_paths,
    )


def resolve_link(vault: VaultConfig, link: str) -> Path | None:
    """Resolve a wikilink target to a Path in the vault, or None if not found."""
    candidates = [
        vault.notes_dir / f"{link}.md",
        vault.notes_dir / link,
        vault.daily_dir / f"{link}.md",
        vault.daily_dir / link,
        vault.tags_dir / f"{link}.md",
        vault.tags_dir / link,
    ]
    return next((path for path in candidates if path.exists()), None)


def find_backlinks(vault: VaultConfig, note_id: str) -> list[Path]:
    """Return all .md files in the vault that link to note_id.

    Note: tags_dir is intentionally excluded. Tag notes are lazy-created,
    so including them would make backlink counts non-deterministic.
    """
    dirs = [d for d in (vault.daily_dir, vault.notes_dir) if d.is_dir()]

    return [
        md_file
        for d in dirs
        for md_file in sorted(d.rglob("*.md"))
        if note_id in extract_links(md_file.read_text(encoding="utf-8"))
    ]


def count_backlinks(vault: VaultConfig) -> dict[str, int]:
    """For every .md in notes/, count how many other files link to it.

    Returns dict mapping note_id (stem) to backlink count.
    """
    if not vault.notes_dir.is_dir():
        return {}

    note_ids = [f.stem for f in vault.notes_dir.glob("*.md")]
    counts: dict[str, int] = {note_id: 0 for note_id in note_ids}

    dirs = [vault.daily_dir, vault.notes_dir]
    for d in dirs:
        if not d.is_dir():
            continue
        for md_file in sorted(d.rglob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            links = extract_links(text)
            for link in links:
                if link in counts:
                    counts[link] += 1

    return counts


def find_orphans(vault: VaultConfig) -> list[Path]:
    """Return notes/ files with zero inbound AND zero outbound links."""
    if not vault.notes_dir.is_dir():
        return []

    backlink_counts = count_backlinks(vault)

    return [
        md_file
        for md_file in sorted(vault.notes_dir.glob("*.md"))
        if not extract_links(md_file.read_text(encoding="utf-8"))
        and backlink_counts.get(md_file.stem, 0) == 0
    ]
