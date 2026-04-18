import re
from mistletoe.span_token import SpanToken
from mistletoe import Document
from mistletoe.block_token import BlockToken
from mistletoe import HTMLRenderer

class WikiLink(SpanToken):
    pattern = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
    def __init__(self, match):
        self.target = match.group(1)

class FrontMatter(BlockToken):
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
    
    @classmethod
    def start(cls, line):
        return line.startswith('---')
        
    @classmethod
    def read(cls, lines):
        line_buffer = [next(lines)]
        for line in lines:
            line_buffer.append(line)
            if line.startswith('---'):
                break
        return line_buffer

    def __init__(self, match):
        self.content = "".join(match)

class MyRenderer(HTMLRenderer):
    def render_wiki_link(self, token):
        return f"<a href='{token.target}'>{token.target}</a>"
    def render_front_matter(self, token):
        return f"<pre>{token.content}</pre>"

text = """---
id: 123
tags: [a, b]
---
# Hello
This is a [[wikilink]] and another [[link|alias]].
"""

with MyRenderer(WikiLink, FrontMatter) as renderer:
    doc = Document(text)
    print("Parsed successfully.")
    for child in doc.children:
        print(type(child))
        if hasattr(child, 'children') and child.children is not None:
            for c in child.children:
                print("  ", type(c), getattr(c, 'content', ''), getattr(c, 'target', ''))
