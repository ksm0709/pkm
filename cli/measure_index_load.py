import time
import sys

sys.path.insert(0, "/home/taeho/repos/pkm/cli/src")

from pkm.config import get_vault
from pkm.search_engine import load_index

vault = get_vault(None)

t0 = time.perf_counter()
index = load_index(vault)
t1 = time.perf_counter()

print(f"Index load time: {(t1 - t0) * 1000:.2f} ms")
print(f"Number of entries in index: {len(index.entries)}")
