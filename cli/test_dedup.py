import sys
from rich.console import Console

console = Console()
try:
    console.print("test", file=sys.stderr)
    print("Success")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
