"""pkm hook command group — lifecycle hooks for LLM agent tool integrations."""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import click


def _safe_hook(fn):
    """Decorator: catch all exceptions, log to stderr, always exit 0."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyboardInterrupt:
            sys.exit(130)  # conventional SIGINT exit code
        except Exception as e:
            import traceback

            print(f"[pkm hook error] {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.exit(0)

    return wrapper


def _load_hook_config(vault) -> dict:
    """Load .pkm/config.toml. Returns {} on missing or parse error."""
    try:
        config_path = vault.pkm_dir / "config.toml"
        if not config_path.exists():
            return {}
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                return {}
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_session_state(vault) -> dict:
    """Load .pkm/session_state.json. Returns defaults on missing or corrupt."""
    defaults: dict = {"session_count": 0, "last_consolidation_at": None}
    try:
        state_path = vault.pkm_dir / "session_state.json"
        if not state_path.exists():
            return defaults.copy()
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return defaults.copy()
        return {
            "session_count": int(data.get("session_count", 0)),
            "last_consolidation_at": data.get("last_consolidation_at"),
        }
    except Exception:
        return defaults.copy()


def _save_session_state(vault, state: dict) -> None:
    """Write .pkm/session_state.json."""
    try:
        vault.pkm_dir.mkdir(parents=True, exist_ok=True)
        state_path = vault.pkm_dir / "session_state.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _check_consolidation_trigger(vault, config: dict) -> str | None:
    """Check if consolidation should be recommended.

    Returns recommendation message string or None.
    Side effect: increments session_count; resets after trigger.
    """
    try:
        from datetime import datetime, timezone, timedelta

        consolidation_cfg = config.get("consolidation", {})
        auto_trigger = consolidation_cfg.get("auto_trigger", True)
        if not auto_trigger:
            return None

        threshold = int(consolidation_cfg.get("session_threshold", 5))
        cooldown_hours = int(consolidation_cfg.get("cooldown_hours", 24))

        state = _load_session_state(vault)
        state["session_count"] = state["session_count"] + 1

        if state["session_count"] < threshold:
            _save_session_state(vault, state)
            return None

        # Check cooldown
        now = datetime.now(timezone.utc)
        last_str = state.get("last_consolidation_at")
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if (now - last_dt) < timedelta(hours=cooldown_hours):
                    _save_session_state(vault, state)
                    return None
            except ValueError:
                pass

        # Find candidates
        from pkm.commands.consolidate import _list_candidate_dates
        candidate_dates = _list_candidate_dates(vault)
        if not candidate_dates:
            state["session_count"] = 0
            _save_session_state(vault, state)
            return None

        # Emit trigger
        state["session_count"] = 0
        state["last_consolidation_at"] = now.isoformat()
        _save_session_state(vault, state)

        lines = [f"{len(candidate_dates)} daily note(s) ready for consolidation. Run:"]
        for d in candidate_dates[:5]:
            lines.append(f"  pkm consolidate mark {d}")
        if len(candidate_dates) > 5:
            lines.append(f"  ... and {len(candidate_dates) - 5} more")
        lines.append("  /pkm:distill-daily")
        return "\n".join(lines)
    except Exception:
        return None


def _handle_session_start(ctx, output_format: str, top: int, **_ignored) -> None:
    vault = ctx.obj["vault"]
    lines = []

    from datetime import date, timedelta

    daily_dir = vault.daily_dir
    for i in range(1, 4):
        d = (date.today() - timedelta(days=i)).isoformat()
        daily_path = daily_dir / f"{d}.md"
        if daily_path.exists():
            text = daily_path.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3 :].strip()
            preview = text[:300].strip()
            if preview:
                if not lines:
                    lines.append("## Recent Daily Notes")
                lines.append(f"### {d}\n{preview}")
                if len([ln for ln in lines if ln.startswith("###")]) >= 2:
                    break

    if lines:
        lines.append("")

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
        pass

    try:
        hook_config = _load_hook_config(vault)
        trigger_msg = _check_consolidation_trigger(vault, hook_config)
        if trigger_msg:
            lines.append("## Consolidation Recommended")
            lines.append(trigger_msg)
            lines.append("")
    except Exception:
        pass

    content = "\n".join(lines).strip()
    if not content:
        content = "PKM memory layer active. Use `pkm note add` to save memories."

    if output_format == "system-reminder":
        click.echo(f"<system-reminder>\n{content}\n</system-reminder>")
    else:
        click.echo(content)


def _handle_turn_start(
    ctx, output_format: str, session_id: str | None, **_ignored
) -> None:
    import json as _json
    import sys as _sys

    vault = ctx.obj["vault"]
    lines: list[str] = []

    # --- Dynamic context injection from stdin + daily note ---
    user_prompt = ""
    if not _sys.stdin.isatty():
        try:
            raw = _sys.stdin.read(65536)  # 64 KB cap — hook payloads are always small
            payload = _json.loads(raw)
            user_prompt = str(payload.get("prompt", ""))
        except Exception:
            pass

    daily_snippet = ""
    try:
        from datetime import date as _date
        today = _date.today().isoformat()
        daily_path = vault.daily_dir / f"{today}.md"
        if daily_path.exists():
            text = daily_path.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            daily_snippet = text[:200]
    except Exception:
        pass

    query_parts = []
    if user_prompt:
        query_parts.append(user_prompt[:150])
    if daily_snippet:
        query_parts.append(daily_snippet[:100])
    query = " ".join(query_parts).strip() or "important decision error finding pattern"

    try:
        from pkm.search_engine import load_index, search as engine_search
        index = load_index(vault)
        results = engine_search(query, index, top_n=3, min_importance=5.0)
        if results:
            lines.append("## Relevant Notes")
            for r in results:
                mt = r.memory_type or "semantic"
                lines.append(f"- [{mt}|imp:{r.importance:.0f}] {r.title}")
            lines.append("")
    except Exception:
        pass

    # --- Advisory text (unchanged from original) ---
    if session_id:
        lines.append(f"Session: {session_id}")
    lines.append(
        "Working memory (daily log): `pkm daily add <text>` to log, `pkm daily` to review today's entries"
    )
    lines.append(
        "Long-term memory: `pkm note add <content> --type semantic|episodic --importance 1-10 --tags <tag1,tag2>`"
    )
    lines.append("Search notes: `pkm search <query>` to recall relevant past knowledge")
    lines.append(
        '  - Before starting work, consider searching: `pkm search "<topic of current task>"`'
    )
    lines.append("  - Read specific notes: `pkm note show <title>`")
    lines.append(
        "For detailed PKM workflows (Zettelkasten, linking, consolidation): invoke the `pkm` skill."
    )
    lines.append("")
    lines.append("PKM Role: You are the active manager of this knowledge base. Before concluding your response, check:")
    lines.append("  - Code changes / bug fixes / new features? → `pkm daily add <summary>`")
    lines.append("  - New concepts / decisions / patterns learned? → `pkm note add <content> --type semantic --importance N`")
    lines.append("  - Important session context to preserve? → `pkm daily add <text>`")

    content = "\n".join(lines)
    if output_format == "system-reminder":
        click.echo(f"<system-reminder>\n{content}\n</system-reminder>")
    else:
        click.echo(content)


def _handle_turn_end(
    ctx, session_id: str | None, summary: str | None, output_format: str, **_ignored
) -> None:
    # Always emit preservation guide
    guide_lines = [
        "Before ending this session, preserve valuable knowledge:",
        '  - Code changes / decisions / patterns? → `pkm daily add "<summary>"`',
        '  - New reusable knowledge? → `pkm note add --content "<insight>" --type semantic --importance N --tags <tags>`',
        '  - Session discoveries worth long-term recall? → `pkm note add --content "<content>" --type episodic --importance N`',
        "",
        "For deeper knowledge workflows (invoke as slash commands):",
        "  - `/pkm:memory-store` — store facts, decisions, and patterns as atomic notes",
        "  - `/pkm:distill-daily` — promote daily insights into permanent knowledge notes",
        "  - `/pkm:zettel-loop` — full knowledge production: distill → connect → tag → structure",
    ]
    guide = "\n".join(guide_lines)
    if output_format == "system-reminder":
        click.echo(f"<system-reminder>\n{guide}\n</system-reminder>")
    else:
        click.echo(guide)

    # Write summary to daily note if provided
    if summary:
        vault = ctx.obj["vault"]
        from datetime import datetime, timezone, date

        now = datetime.now(timezone.utc)
        today = date.today().isoformat()
        daily_dir = vault.daily_dir
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_path = daily_dir / f"{today}.md"
        if not daily_path.resolve().is_relative_to(daily_dir.resolve()):
            raise RuntimeError("Resolved daily path escapes daily_dir — aborting write.")
        session_tag = f" [session:{session_id}]" if session_id else ""
        entry = f"- {now.strftime('%H:%M')}{session_tag} {summary}\n"
        if daily_path.exists():
            with daily_path.open("a", encoding="utf-8") as f:
                f.write(entry)
        else:
            daily_path.write_text(f"# {today}\n\n{entry}", encoding="utf-8")


def _handle_turn_end_exit2(ctx, **_ignored) -> None:
    """Exit-2 blocking hook for opencode/omo Stop event.

    Reads stdin JSON. If stop_hook_active guard is set, exits 0 (prevent infinite loop).
    If no transcript_path, exits 0. Otherwise writes extraction instructions to stderr
    and exits 2 (signals the main agent to continue working).
    """
    payload: dict = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read(65536)
            payload = json.loads(raw)
        except Exception:
            pass

    if payload.get("stop_hook_active", False):
        sys.exit(0)

    transcript_path = payload.get("transcript_path", "")
    if not transcript_path:
        sys.exit(0)

    instructions = """\
KNOWLEDGE EXTRACTION TASK: Before stopping, extract knowledge from this session.
Use your Read tool to read the session transcript at: {transcript_path}
Then:
1. Identify: key decisions, bugs fixed, patterns learned, new concepts discovered
2. For session entries: run `pkm daily add '<summary>'` via your Bash tool
3. For reusable knowledge: run `pkm note add '<content>' --type semantic --importance <5-9> --tags <tags>` via your Bash tool
4. Run: `pkm daily add '<one-sentence session summary>'`
Be selective — skip trivial facts. Quality over quantity.
Then you may stop.""".format(transcript_path=transcript_path)

    print(instructions, file=sys.stderr)
    sys.exit(2)


def _handle_migrate(dry_run: bool) -> None:
    """Remove PKM hooks from ~/.claude/settings.json, keep all other hooks."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        click.echo("~/.claude/settings.json not found — nothing to migrate.")
        return

    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as e:
        click.echo(f"Error reading settings.json: {e}", err=True)
        return

    hooks = existing.get("hooks", {})
    removed_counts: dict[str, int] = {}

    def _is_pkm_hook(hook_entry: dict) -> bool:
        cmd = hook_entry.get("command", "")
        return "pkm hook run" in cmd or "pkm agent hook" in cmd

    for event, matchers in list(hooks.items()):
        filtered = []
        removed = 0
        for matcher in matchers:
            matcher_hooks = matcher.get("hooks", [])
            non_pkm = [h for h in matcher_hooks if not _is_pkm_hook(h)]
            if len(non_pkm) < len(matcher_hooks):
                removed += len(matcher_hooks) - len(non_pkm)
            if non_pkm:
                matcher = {**matcher, "hooks": non_pkm}
                filtered.append(matcher)
        hooks[event] = filtered
        if removed:
            removed_counts[event] = removed

    # Remove event keys with empty matcher lists
    hooks = {k: v for k, v in hooks.items() if v}
    existing["hooks"] = hooks

    if not removed_counts:
        click.echo("No PKM hooks found in ~/.claude/settings.json — nothing to remove.")
        return

    for event, count in removed_counts.items():
        action = "Would remove" if dry_run else "Removed"
        click.echo(f"  {action} {count} PKM hook(s) from {event}")

    if dry_run:
        click.echo("Dry run — no changes written.")
        return

    import os
    import stat

    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    os.chmod(settings_path, stat.S_IRUSR | stat.S_IWUSR)
    click.echo(f"Updated {settings_path}")


@click.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """Lifecycle hook handlers for LLM agent integrations."""


@hook.command(name="run")
@click.argument(
    "hook_name",
    metavar="HOOK_NAME",
    type=click.Choice(["session-start", "turn-start", "turn-end", "turn-end-exit2"]),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["plain", "system-reminder"]),
    default="plain",
)
@click.option(
    "--top", default=5, help="Number of recent memories to inject (session-start only)"
)
@click.option("--session", "session_id", default=None, help="Session ID")
@click.option("--summary", default=None, help="Summary to persist (turn-end only)")
@click.pass_context
@_safe_hook
def run_hook(
    ctx: click.Context,
    hook_name: str,
    output_format: str,
    top: int,
    session_id: str | None,
    summary: str | None,
) -> None:
    """Run a lifecycle hook handler.

    HOOK_NAME: session-start | turn-start | turn-end | turn-end-exit2
    """
    kwargs = dict(
        output_format=output_format, top=top, session_id=session_id, summary=summary
    )
    if hook_name == "session-start":
        _handle_session_start(ctx, **kwargs)
    elif hook_name == "turn-start":
        _handle_turn_start(ctx, **kwargs)
    elif hook_name == "turn-end":
        _handle_turn_end(ctx, **kwargs)
    elif hook_name == "turn-end-exit2":
        _handle_turn_end_exit2(ctx, **kwargs)


@hook.command(name="setup")
@click.option("--tool", type=click.Choice(["claude-code", "codex"]), required=True)
@click.option("--dry-run", is_flag=True, help="Print config without writing")
@click.pass_context
def setup(ctx: click.Context, tool: str, dry_run: bool) -> None:
    """Print hook install instructions for the specified agent tool.

    - claude-code: prints plugin install instructions
    - codex: prints codex/hooks.json install instructions
    """
    if tool == "claude-code":
        _setup_claude_code_hooks(dry_run)
    elif tool == "codex":
        _setup_codex_hooks(dry_run)


@hook.command(name="migrate")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without writing")
@click.pass_context
def migrate(ctx: click.Context, dry_run: bool) -> None:
    """Remove old PKM hooks from ~/.claude/settings.json.

    Removes hook entries added by 'pkm hook setup --tool claude-code'.
    Keeps all other hooks (OMC, TypeScript LSP, etc.) intact.
    """
    _handle_migrate(dry_run)


def _setup_claude_code_hooks(dry_run: bool) -> None:
    """Print Claude Code plugin install instructions."""
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[4]
    plugin_hooks = repo_root / "plugin" / "hooks" / "hooks.json"

    click.echo("PKM Claude Code Plugin — install instructions:")
    click.echo("")
    click.echo("The PKM plugin uses Claude Code's plugin system for hook isolation.")
    click.echo("This keeps PKM hooks separate from ~/.claude/settings.json.")
    click.echo("")
    click.echo("Install via Claude Code plugin marketplace (recommended):")
    click.echo("  Run Claude Code and add the plugin from the plugin marketplace.")
    click.echo("")
    click.echo("Or install manually:")
    click.echo(f"  Plugin hooks file: {plugin_hooks}")
    click.echo("")
    click.echo("To remove old PKM hooks from ~/.claude/settings.json, run:")
    click.echo("  pkm hook migrate")


def _setup_codex_hooks(dry_run: bool) -> None:
    """Print Codex CLI hook install instructions."""
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[4]
    codex_hooks = repo_root / "codex" / "hooks.json"

    click.echo("PKM Codex hooks — install instructions:")
    click.echo("")
    click.echo(f"  Source: {codex_hooks}")
    click.echo("")
    click.echo("Install (copy):")
    click.echo(f"  cp {codex_hooks} ~/.codex/hooks.json")
    click.echo("")
    click.echo("Install (symlink — auto-updates when PKM updates):")
    click.echo(f"  ln -sf {codex_hooks} ~/.codex/hooks.json")
