import re
import urllib.request
from pathlib import Path

def get_changelog(latest_n: int | None = None, since_version: str | None = None) -> str:
    """Fetch and parse CHANGELOG.md, returning markdown string."""
    # Try finding it in the parent directories (local repo checkout)
    current_dir = Path(__file__).resolve().parent
    possible_paths = [
        current_dir.parent.parent.parent / "CHANGELOG.md",
        current_dir.parent.parent / "CHANGELOG.md",
    ]
    
    content = ""
    for path in possible_paths:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            break
            
    if not content:
        # Fallback to fetching from github
        try:
            req = urllib.request.urlopen("https://raw.githubusercontent.com/ksm0709/pkm/main/CHANGELOG.md", timeout=3)
            content = req.read().decode('utf-8')
        except Exception:
            return ""

    # Split by the version header: e.g. "## v2.30.0 (2026-04-18)"
    sections = re.split(r'\n## (v[0-9]+\.[0-9]+\.[0-9]+.*)\n', content)
    if len(sections) < 3:
        return ""

    parsed = []
    for i in range(1, len(sections), 2):
        header = "## " + sections[i]
        body = sections[i+1].strip()
        parsed.append((header, body))

    if latest_n:
        return "\n\n".join(f"{h}\n\n{b}" for h, b in parsed[:latest_n])

    if since_version:
        since_v = since_version if since_version.startswith("v") else f"v{since_version}"
        idx = -1
        for i, (h, b) in enumerate(parsed):
            if since_v in h:
                idx = i
                break
        
        if idx > 0:
            return "\n\n".join(f"{h}\n\n{b}" for h, b in parsed[:idx])
        elif idx == 0:
            return "No new changes."
        
    return ""
