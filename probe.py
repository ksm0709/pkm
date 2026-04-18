import networkx as nx
import json
import time
import os
import tracemalloc

# Generate dummy graph
G = nx.fast_gnp_random_graph(10000, 0.001, directed=True)
print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

# Serialize
start = time.time()
data = nx.node_link_data(G)
with open("dummy_graph.json", "w") as f:
    json.dump(data, f)
print(f"Serialize time: {time.time() - start:.4f}s")
print(f"File size: {os.path.getsize('dummy_graph.json') / 1024 / 1024:.2f} MB")

# Deserialize and measure memory
tracemalloc.start()
start = time.time()
with open("dummy_graph.json", "r") as f:
    loaded_data = json.load(f)
loaded_G = nx.node_link_graph(loaded_data)
load_time = time.time() - start
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

print(f"Deserialize time: {load_time:.4f}s")
print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
