"""
Shared interface contract for PKM memory layer.
All workstreams (WS-1, WS-2, WS-3, WS-4) must import from here to stay in sync.
"""

from __future__ import annotations

# Memory type literals
MEMORY_TYPE_EPISODIC = "episodic"
MEMORY_TYPE_SEMANTIC = "semantic"
MEMORY_TYPE_PROCEDURAL = "procedural"
MEMORY_TYPES = [MEMORY_TYPE_EPISODIC, MEMORY_TYPE_SEMANTIC, MEMORY_TYPE_PROCEDURAL]

# Source type literals
SOURCE_TYPE_AGENT = "agent"
SOURCE_TYPE_HUMAN = "human"
SOURCE_TYPE_CONSOLIDATION = "consolidation"
SOURCE_TYPES = [SOURCE_TYPE_AGENT, SOURCE_TYPE_HUMAN, SOURCE_TYPE_CONSOLIDATION]

# Importance range
IMPORTANCE_MIN = 1.0
IMPORTANCE_MAX = 10.0
IMPORTANCE_DEFAULT = 5.0

# Default field values (used by frontmatter generator and IndexEntry)
MEMORY_FIELD_DEFAULTS = {
    "memory_type": MEMORY_TYPE_SEMANTIC,
    "importance": IMPORTANCE_DEFAULT,
    "created_at": None,  # ISO 8601 datetime string
    "session_id": None,  # UUID short string
    "agent_id": None,  # agent identifier
    "source_type": SOURCE_TYPE_AGENT,
    "consolidated": False,
}

# Schema version for VectorIndex — bump when IndexEntry fields change
CURRENT_SCHEMA_VERSION = 2
