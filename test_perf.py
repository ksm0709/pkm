import time
import re
from mistletoe import Document, HTMLRenderer
from test_mistletoe_custom import WikiLink, FrontMatter, MyRenderer

text = """---
id: 123
tags: [a, b]
---
# Hello
This is a [[wikilink]] and another [[link|alias]].
""" * 100

# Regex approach
start = time.time()
_LINK_PATTERN = re.compile(r"(?<!\!)\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
for _ in range(1000):
    t = _CODE_BLOCK.sub("", text)
    links = _LINK_PATTERN.findall(t)
regex_time = time.time() - start

# Mistletoe approach
start = time.time()
for _ in range(1000):
    with MyRenderer(WikiLink, FrontMatter) as renderer:
        doc = Document(text)
        # We would need to traverse the AST to find WikiLinks
        def find_links(node):
            links = []
            if isinstance(node, WikiLink):
                links.append(node.target)
            if hasattr(node, 'children') and node.children:
                for child in node.children:
                    links.extend(find_links(child))
            return links
        links = find_links(doc)
mistletoe_time = time.time() - start

print(f"Regex time: {regex_time:.4f}s")
print(f"Mistletoe time: {mistletoe_time:.4f}s")
print(f"Ratio: {mistletoe_time / regex_time:.2f}x slower")
