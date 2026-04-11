import time
import sys
import json

sys.path.insert(0, "/home/taeho/repos/pkm/cli/src")

from pkm.config import get_vault
from pkm.search_engine import IndexEntry, VectorIndex

vault = get_vault(None)

# Create a huge dummy index to simulate a very large vault
dummy_index_path = vault.pkm_dir / "index_huge.json"
entries = []
for i in range(10000):
    entries.append(
        {
            "note_id": f"note_{i}",
            "path": f"/path/to/note_{i}.md",
            "embedding": [0.1] * 384,
            "backlink_count": 0,
            "tags": ["tag1"],
            "title": f"Note {i}",
            "memory_type": "semantic",
            "importance": 7.0,
            "created_at": "2026-04-11T00:00:00+00:00",
        }
    )

dummy_data = {
    "model": "all-MiniLM-L6-v2",
    "created_at": "2026-04-11T00:00:00+00:00",
    "schema_version": 2,
    "entries": entries,
}

dummy_index_path.write_text(json.dumps(dummy_data))

t0 = time.perf_counter()
# Mock load_index to read our dummy file
data = json.loads(dummy_index_path.read_text(encoding="utf-8"))
loaded_entries = [
    IndexEntry(**{k: v for k, v in e.items() if k in IndexEntry.__dataclass_fields__})
    for e in data["entries"]
]
VectorIndex(
    model=data["model"],
    created_at=data["created_at"],
    entries=loaded_entries,
    schema_version=data.get("schema_version", 1),
)
t1 = time.perf_counter()

print(f"Index load time (10,000 entries): {(t1 - t0) * 1000:.2f} ms")
print(f"File size: {dummy_index_path.stat().st_size / 1024 / 1024:.2f} MB")
