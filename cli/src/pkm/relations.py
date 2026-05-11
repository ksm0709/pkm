"""Markdown-derived relation parsing, vocabulary, and audit helpers."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pkm.config import VaultConfig
from pkm.frontmatter import generate_frontmatter, parse, render
from pkm.wikilinks import match_wikilink_at_start


BUILT_IN_RELATIONS: dict[str, str] = {
    "is_a": "Class or category relation.",
    "part_of": "Whole-part relation.",
    "depends_on": "Source requires target.",
    "enables": "Source makes target possible.",
    "contrasts_with": "Source differs meaningfully from target.",
    "supersedes": "Source replaces target.",
    "instance_of": "Concrete instance of a type.",
    "related": "General typed relation.",
    "source": "Source material or evidence relation.",
}

RELATION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_MARKER_PATTERN = re.compile(r"(?<![\w/])&([A-Za-z][A-Za-z0-9_]*)\b")
_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True)
class RelationMarker:
    type: str
    target: str
    reason: str | None
    line: int
    source_path: str | None = None

    def to_edge_metadata(self, source_path: str) -> dict[str, Any]:
        return {
            "type": self.type,
            "reason": self.reason,
            "source": {"path": source_path, "line": self.line},
        }


@dataclass(frozen=True)
class RelationParseResult:
    markers: list[RelationMarker]
    malformed: list[dict[str, Any]]


@dataclass
class RelationVocabularyEntry:
    type: str
    description: str = ""
    status: str = "vault"
    aliases: list[str] = field(default_factory=list)
    inverse: str | None = None
    examples: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationScanRecord:
    marker: RelationMarker
    note_id: str
    note_title: str
    source_path: str
    source_kind: str


@dataclass
class RelationState:
    built_in: dict[str, RelationVocabularyEntry]
    vault: dict[str, RelationVocabularyEntry]
    observed: dict[str, dict[str, Any]]
    audit: dict[str, Any]
    records: list[RelationScanRecord]


def is_valid_relation_name(name: str) -> bool:
    return bool(RELATION_NAME_PATTERN.fullmatch(name))


def iter_relation_markdown_files(vault: VaultConfig) -> list[Path]:
    """Return the same non-recursive Markdown scope used by graph indexing."""
    files: list[Path] = []
    for directory in (vault.notes_dir, vault.daily_dir, vault.tags_dir):
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.md")))
    return files


def parse_relation_markers(
    text: str, *, source_path: str | None = None
) -> RelationParseResult:
    """Parse `&relation [[Target]]` markers from Markdown, excluding fences."""
    markers: list[RelationMarker] = []
    malformed: list[dict[str, Any]] = []
    in_fence = False

    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for marker_match in _MARKER_PATTERN.finditer(line):
            relation_type = marker_match.group(1)
            tail = line[marker_match.end() :]
            tail_stripped = tail.lstrip()
            if not tail or tail == tail_stripped:
                malformed.append(
                    _malformed_marker(relation_type, line_no, source_path, line)
                )
                continue

            link = match_wikilink_at_start(tail_stripped)
            if link is None:
                malformed.append(
                    _malformed_marker(relation_type, line_no, source_path, line)
                )
                continue

            target, link_end = link
            reason_tail = tail_stripped[link_end:].strip()
            reason = None
            if reason_tail.startswith("-"):
                reason = reason_tail[1:].strip() or None
            markers.append(
                RelationMarker(
                    type=relation_type,
                    target=target,
                    reason=reason,
                    line=line_no,
                    source_path=source_path,
                )
            )

    return RelationParseResult(markers=markers, malformed=malformed)


def parse_vault_vocabulary(text: str) -> dict[str, RelationVocabularyEntry]:
    """Parse the documented `## relation_name` vocabulary note grammar."""
    body = _FRONTMATTER_PATTERN.sub("", text, count=1)
    entries: dict[str, RelationVocabularyEntry] = {}
    current: RelationVocabularyEntry | None = None

    for raw_line in body.splitlines():
        line = raw_line.strip()
        heading = _HEADING_PATTERN.match(line)
        if heading:
            name = heading.group(1).strip()
            current = None
            if is_valid_relation_name(name):
                current = RelationVocabularyEntry(type=name)
                entries[name] = current
            continue

        if current is None or not line:
            continue

        if line.startswith("-"):
            key, sep, value = line[1:].strip().partition(":")
            if not sep:
                continue
            key = key.strip().lower()
            value = value.strip()
            if key == "description":
                current.description = value
            elif key == "aliases":
                current.aliases = [v.strip() for v in value.split(",") if v.strip()]
            elif key == "inverse":
                current.inverse = value or None
            elif key == "example" and value:
                current.examples.append(value)
            continue

        if not current.description:
            current.description = line

    return entries


def collect_relation_state(vault: VaultConfig) -> RelationState:
    files = iter_relation_markdown_files(vault)
    note_ids = _collect_note_ids(files)
    vault_entries = _load_vault_vocabulary(vault)
    built_in = {
        name: RelationVocabularyEntry(
            type=name, description=description, status="built_in"
        )
        for name, description in BUILT_IN_RELATIONS.items()
    }
    known_vocab = set(built_in) | set(vault_entries)

    records: list[RelationScanRecord] = []
    malformed: list[dict[str, Any]] = []

    for file_path in files:
        try:
            note = parse(file_path)
        except Exception:
            continue
        source_path = _relative_path(vault, file_path)
        source_kind = _source_kind(vault, file_path)
        parsed = parse_relation_markers(note.body, source_path=source_path)
        malformed.extend(parsed.malformed)
        for marker in parsed.markers:
            records.append(
                RelationScanRecord(
                    marker=marker,
                    note_id=str(note.id),
                    note_title=note.title,
                    source_path=source_path,
                    source_kind=source_kind,
                )
            )

    observed = _build_observed(records, known_vocab)
    audit = _build_audit(records, malformed, known_vocab, note_ids)
    return RelationState(
        built_in=built_in,
        vault=vault_entries,
        observed=observed,
        audit=audit,
        records=records,
    )


def write_relation_outputs(vault: VaultConfig, state: RelationState) -> None:
    vault.pkm_dir.mkdir(parents=True, exist_ok=True)
    vault.relations_vocabulary_path.write_text(
        json.dumps(vocabulary_payload(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    vault.relations_audit_path.write_text(
        json.dumps(audit_payload(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def vocabulary_payload(state: RelationState) -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "scan_scope": "top-level notes/daily/tags markdown files",
        "built_in": {
            name: asdict(entry) for name, entry in sorted(state.built_in.items())
        },
        "vault": {name: asdict(entry) for name, entry in sorted(state.vault.items())},
        "observed": dict(sorted(state.observed.items())),
    }


def audit_payload(state: RelationState) -> dict[str, Any]:
    return {"generated_at": _now(), **state.audit}


def load_or_scan_relation_payloads(
    vault: VaultConfig,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if _cache_is_fresh(vault):
        return (
            json.loads(vault.relations_vocabulary_path.read_text(encoding="utf-8")),
            json.loads(vault.relations_audit_path.read_text(encoding="utf-8")),
            "fresh_cache",
        )
    state = collect_relation_state(vault)
    return vocabulary_payload(state), audit_payload(state), "live_scan"


def promote_relation(vault: VaultConfig, relation_type: str) -> Path:
    if not is_valid_relation_name(relation_type):
        raise ValueError(f"Invalid relation name: {relation_type!r}")

    path = vault.notes_dir / "pkm-relation-vocabulary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        entries = parse_vault_vocabulary(text)
        if relation_type in entries:
            return path
        body = text.rstrip() + f"\n\n## {relation_type}\n\n- Description: \n"
        path.write_text(body + "\n", encoding="utf-8")
        return path

    meta = generate_frontmatter(
        note_id="pkm-relation-vocabulary",
        tags=[],
        type="index",
        description="Vault-local PKM relation vocabulary.",
    )
    body = (
        "Vault-local PKM relation vocabulary.\n\n"
        f"## {relation_type}\n\n"
        "- Description: \n"
    )
    path.write_text(render(meta, body), encoding="utf-8")
    return path


def _build_observed(
    records: list[RelationScanRecord], known_vocab: set[str]
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[RelationScanRecord]] = defaultdict(list)
    for record in records:
        grouped[record.marker.type].append(record)

    observed: dict[str, dict[str, Any]] = {}
    for relation_type, items in grouped.items():
        source_counts = Counter(item.note_id for item in items)
        target_counts = Counter(item.marker.target for item in items)
        observed[relation_type] = {
            "type": relation_type,
            "count": len(items),
            "status": "known" if relation_type in known_vocab else "observed",
            "examples": [_record_to_usage(item) for item in items[:5]],
            "common_sources": [
                {"source": source, "count": count}
                for source, count in source_counts.most_common(5)
            ],
            "common_targets": [
                {"target": target, "count": count}
                for target, count in target_counts.most_common(5)
            ],
        }
    return observed


def _build_audit(
    records: list[RelationScanRecord],
    malformed: list[dict[str, Any]],
    known_vocab: set[str],
    note_ids: set[str],
) -> dict[str, Any]:
    canonical = [record for record in records if record.source_kind == "notes"]
    pair_to_types: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in canonical:
        pair_to_types[(record.note_id, record.marker.target)].append(record.marker.type)

    return {
        "malformed_markers": malformed,
        "missing_reasons": [
            _record_to_usage(record) for record in canonical if not record.marker.reason
        ],
        "unresolved_targets": [
            _record_to_usage(record)
            for record in canonical
            if record.marker.target not in note_ids
        ],
        "unknown_relations": [
            _record_to_usage(record)
            for record in canonical
            if record.marker.type not in known_vocab
        ],
        "near_duplicate_relations": [],
        "low_frequency_relations": _low_frequency(records),
        "multiple_relations": [
            {"source": source, "target": target, "types": types}
            for (source, target), types in sorted(pair_to_types.items())
            if len(set(types)) > 1
        ],
        "daily_promotion_candidates": [
            _record_to_usage(record)
            for record in records
            if record.source_kind == "daily"
        ],
    }


def _load_vault_vocabulary(vault: VaultConfig) -> dict[str, RelationVocabularyEntry]:
    path = vault.notes_dir / "pkm-relation-vocabulary.md"
    if not path.exists():
        return {}
    return parse_vault_vocabulary(path.read_text(encoding="utf-8"))


def _collect_note_ids(files: list[Path]) -> set[str]:
    note_ids: set[str] = set()
    for path in files:
        try:
            note_ids.add(str(parse(path).id))
        except Exception:
            continue
    return note_ids


def _low_frequency(records: list[RelationScanRecord]) -> list[dict[str, Any]]:
    counts = Counter(record.marker.type for record in records)
    return [
        {"type": relation_type, "count": count}
        for relation_type, count in sorted(counts.items())
        if count == 1
    ]


def _record_to_usage(record: RelationScanRecord) -> dict[str, Any]:
    payload = {
        "type": record.marker.type,
        "target": record.marker.target,
        "reason": record.marker.reason,
        "source": {"path": record.source_path, "line": record.marker.line},
    }
    if record.note_id:
        payload["source_note"] = record.note_id
    return payload


def _malformed_marker(
    relation_type: str, line: int, source_path: str | None, text: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": relation_type,
        "line": line,
        "text": text.strip(),
    }
    if source_path is not None:
        payload["source"] = {"path": source_path, "line": line}
    return payload


def _relative_path(vault: VaultConfig, path: Path) -> str:
    try:
        return path.relative_to(vault.path).as_posix()
    except ValueError:
        return path.as_posix()


def _source_kind(vault: VaultConfig, path: Path) -> str:
    parent = path.parent.resolve()
    if vault.notes_dir.is_dir() and parent == vault.notes_dir.resolve():
        return "notes"
    if vault.daily_dir.is_dir() and parent == vault.daily_dir.resolve():
        return "daily"
    if vault.tags_dir.is_dir() and parent == vault.tags_dir.resolve():
        return "tags"
    return "other"


def _cache_is_fresh(vault: VaultConfig) -> bool:
    paths = [vault.relations_vocabulary_path, vault.relations_audit_path]
    if not all(path.exists() for path in paths):
        return False
    source_mtime = max(
        (path.stat().st_mtime for path in iter_relation_markdown_files(vault)),
        default=0,
    )
    cache_mtime = min(path.stat().st_mtime for path in paths)
    return cache_mtime >= source_mtime


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
