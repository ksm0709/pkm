"""pkm agent command group — hook handlers for LLM agent tool integrations."""
from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import click


def _safe_hook(fn):
    """Decorator: catch all exceptions, log to stderr, always exit 0.
    Hooks must never crash the agent's session."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except BaseException as e:
            import traceback
            print(f"[pkm hook error] {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.exit(0)
    return wrapper


@click.group()
@click.pass_context
def agent(ctx: click.Context) -> None:
    """Agent tool integration: hooks and setup."""


@agent.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """Lifecycle hook handlers."""


@hook.command(name="session-start")
@click.option("--format", "output_format", type=click.Choice(["plain", "system-reminder"]), default="plain")
@click.option("--top", default=5, help="Number of recent memories to inject")
@click.pass_context
@_safe_hook
def session_start(ctx: click.Context, output_format: str, top: int) -> None:
    """Inject recent memories and daily context at session start.

    Used in Claude Code SessionStart hook, Codex session-start hook,
    and opencode via oh-my-opencode bridge.
    """
    vault = ctx.obj["vault"]

    lines = []

    # Recent daily notes summary (last 3 days)
    from datetime import date, timedelta
    daily_dir = vault.daily_dir
    for i in range(1, 4):  # yesterday, 2 days ago, 3 days ago
        d = (date.today() - timedelta(days=i)).isoformat()
        daily_path = daily_dir / f"{d}.md"
        if daily_path.exists():
            text = daily_path.read_text(encoding="utf-8")
            # Strip frontmatter
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            preview = text[:300].strip()
            if preview:
                if not lines:
                    lines.append("## Recent Daily Notes")
                lines.append(f"### {d}\n{preview}")
                if len([l for l in lines if l.startswith("###")]) >= 2:
                    break

    if lines:
        lines.append("")

    # Top recent memories via search index (if index exists)
    try:
        from pkm.search_engine import load_index, search as engine_search
        index = load_index(vault)
        results = engine_search(
            "important decision error finding pattern",
            index,
            top_n=top,
            recency_weight=0.4,
            min_importance=6.0,
        )
        if results:
            lines.append("## Recent Memories")
            for r in results:
                mt = r.memory_type or "semantic"
                lines.append(f"- [{mt}|imp:{r.importance:.0f}] {r.title}")
            lines.append("")
    except Exception:
        pass  # Search index may not exist yet

    content = "\n".join(lines).strip()
    if not content:
        content = "PKM memory layer active. Use `pkm memory store` to save memories."

    if output_format == "system-reminder":
        click.echo(f"<system-reminder>\n{content}\n</system-reminder>")
    else:
        click.echo(content)


@hook.command(name="turn-start")
@click.option("--format", "output_format", type=click.Choice(["plain", "system-reminder"]), default="plain")
@click.option("--session", "session_id", default=None)
@click.pass_context
@_safe_hook
def turn_start(ctx: click.Context, output_format: str, session_id: str | None) -> None:
    """Lightweight context refresh at turn start.

    Used in Claude Code UserPromptSubmit hook, Codex turn-start hook.
    """
    lines = []
    if session_id:
        lines.append(f"Session: {session_id}")
    lines.append("Memory: `pkm memory store <content> --type semantic|episodic --importance 1-10`")
    lines.append("Search: `pkm memory search <query>`")

    content = "\n".join(lines)
    if output_format == "system-reminder":
        click.echo(f"<system-reminder>\n{content}\n</system-reminder>")
    else:
        click.echo(content)


@hook.command(name="turn-end")
@click.option("--session", "session_id", default=None)
@click.option("--summary", default=None, help="Optional summary to append to daily note")
@click.pass_context
@_safe_hook
def turn_end(ctx: click.Context, session_id: str | None, summary: str | None) -> None:
    """Persist turn summary to daily note.

    Used in Claude Code Stop hook, Codex turn-end hook.
    Silent by default (no output needed for Stop hooks).
    """
    if not summary:
        return  # Nothing to persist

    vault = ctx.obj["vault"]
    from datetime import datetime, timezone, date
    now = datetime.now(timezone.utc)
    today = date.today().isoformat()
    daily_dir = vault.daily_dir
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_path = daily_dir / f"{today}.md"

    session_tag = f" [session:{session_id}]" if session_id else ""
    entry = f"- {now.strftime('%H:%M')}{session_tag} {summary}\n"

    if daily_path.exists():
        with daily_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    else:
        daily_path.write_text(f"# {today}\n\n{entry}", encoding="utf-8")


@agent.command(name="setup-hooks")
@click.option("--tool", type=click.Choice(["claude-code", "codex", "opencode"]), required=True)
@click.option("--dry-run", is_flag=True, help="Print config without writing")
@click.pass_context
def setup_hooks(ctx: click.Context, tool: str, dry_run: bool) -> None:
    """Write hook configuration for the specified agent tool.

    Supported tools:
    - claude-code: writes to ~/.claude/settings.json
    - codex: prints config for ~/.codex/config.toml
    - opencode: prints oh-my-opencode bridge setup instructions
    """
    if tool == "claude-code":
        _setup_claude_code_hooks(dry_run)
    elif tool == "codex":
        _setup_codex_hooks(dry_run)
    elif tool == "opencode":
        _setup_opencode_hooks(dry_run)


def _setup_claude_code_hooks(dry_run: bool) -> None:
    """Write hooks to ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    hooks = {
        "SessionStart": [{"hooks": [{"type": "command", "command": "pkm agent hook session-start --format system-reminder"}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "pkm agent hook turn-start --format system-reminder"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "pkm agent hook turn-end"}]}],
    }

    config_snippet = json.dumps({"hooks": hooks}, indent=2)

    if dry_run:
        click.echo("# Claude Code hooks configuration (add to ~/.claude/settings.json):")
        click.echo(config_snippet)
        return

    existing.setdefault("hooks", {}).update(hooks)
    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    click.echo(f"Wrote hooks to {settings_path}")


def _setup_codex_hooks(dry_run: bool) -> None:
    """Print Codex CLI hook configuration instructions."""
    config = (
        "# Add to ~/.codex/config.toml:\n"
        "[hooks]\n"
        'session_start = "pkm agent hook session-start --format system-reminder"\n'
        'user_prompt_submit = "pkm agent hook turn-start --format system-reminder"\n'
        'stop = "pkm agent hook turn-end"\n'
    )
    if dry_run:
        click.echo(config)
        return
    click.echo("Add the following to ~/.codex/config.toml:")
    click.echo(config)


def _setup_opencode_hooks(dry_run: bool) -> None:
    """Print opencode / oh-my-opencode bridge setup instructions."""
    instructions = (
        "# opencode hook setup via oh-my-opencode bridge:\n"
        "# oh-my-opencode bridges Claude Code plugin hooks to opencode.\n"
        "# The HooksConfig format and injectHookMessage API are supported.\n"
        "#\n"
        "# In your oh-my-opencode plugin config:\n"
        "# {\n"
        '#   "hooks": {\n'
        '#     "SessionStart":     [{"type": "command", "command": "pkm agent hook session-start --format system-reminder"}],\n'
        '#     "UserPromptSubmit": [{"type": "command", "command": "pkm agent hook turn-start --format system-reminder"}],\n'
        '#     "Stop":             [{"type": "command", "command": "pkm agent hook turn-end"}]\n'
        "#   }\n"
        "# }\n"
        "#\n"
        "# See: ~/.npm-global/lib/node_modules/oh-my-opencode/ for integration details.\n"
    )
    click.echo(instructions)
