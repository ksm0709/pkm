import mistletoe
from mistletoe import Document

text = """---
id: 123
tags: [a, b]
---
# Hello
This is a [[wikilink]] and another [[link|alias]].
"""

try:
    doc = Document(text)
    print("Mistletoe parsed successfully.")
    for child in doc.children:
        print(type(child))
        if hasattr(child, 'children') and child.children is not None:
            for c in child.children:
                print("  ", type(c), getattr(c, 'content', ''))
except Exception as e:
    print(f"Error: {e}")
