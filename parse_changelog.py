import re
from pathlib import Path
import urllib.request

def get_changelog(latest_n=None, since_version=None):
    changelog_path = Path("/home/taeho/repos/pkm/CHANGELOG.md")
    content = ""
    if changelog_path.exists():
        content = changelog_path.read_text(encoding="utf-8")
    else:
        try:
            req = urllib.request.urlopen("https://raw.githubusercontent.com/ksm0709/pkm/main/CHANGELOG.md", timeout=5)
            content = req.read().decode('utf-8')
        except Exception:
            return ""

    # Parse sections
    # ## v2.30.0 (2026-04-18)
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
        # find the index of since_version
        idx = -1
        since_v = since_version if since_version.startswith("v") else f"v{since_version}"
        for i, (h, b) in enumerate(parsed):
            if since_v in h:
                idx = i
                break
                
        if idx > 0:
            return "\n\n".join(f"{h}\n\n{b}" for h, b in parsed[:idx])
        elif idx == 0:
            return "No new changes."
        else:
            return ""

print(get_changelog(latest_n=3))
print("-----")
print(get_changelog(since_version="v2.28.3"))
