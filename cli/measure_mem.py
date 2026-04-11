import os

try:
    import psutil
except ImportError:
    os.system("uv pip install psutil")
    import psutil
from sentence_transformers import SentenceTransformer

process = psutil.Process(os.getpid())
mem_before = process.memory_info().rss / 1024 / 1024
print(f"Memory before: {mem_before:.2f} MB")

model = SentenceTransformer("all-MiniLM-L6-v2")

mem_after = process.memory_info().rss / 1024 / 1024
print(f"Memory after: {mem_after:.2f} MB")
print(f"Delta: {mem_after - mem_before:.2f} MB")
