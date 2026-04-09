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


@click.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """Lifecycle hook handlers for LLM agent integrations."""


@hook.command(name="run")
@click.argument(
    "hook_name",
    metavar="HOOK_NAME",
    type=click.Choice(["session-start", "turn-start", "turn-end"]),
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

    HOOK_NAME: session-start | turn-start | turn-end
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


@hook.command(name="setup")
@click.option("--tool", type=click.Choice(["claude-code", "codex"]), required=True)
@click.option("--dry-run", is_flag=True, help="Print config without writing")
@click.pass_context
def setup(ctx: click.Context, tool: str, dry_run: bool) -> None:
    """Write hook configuration for the specified agent tool.

    - claude-code: appends to ~/.claude/settings.json (preserves existing hooks)
    - codex: prints config for ~/.codex/config.toml
    """
    if tool == "claude-code":
        _setup_claude_code_hooks(dry_run)
    elif tool == "codex":
        _setup_codex_hooks(dry_run)


def _merge_claude_hooks(existing_hooks: dict, pkm_hooks: dict) -> dict:
    """Merge pkm hooks into existing hooks without overwriting.

    Uses exact equality (==) for idempotency check — NOT substring match.
    Appends new matcher entries; never modifies existing matchers.
    """
    for event, pkm_matchers in pkm_hooks.items():
        existing_matchers = list(existing_hooks.get(event, []))
        pkm_cmd = pkm_matchers[0]["hooks"][0]["command"]
        already_registered = any(
            any(pkm_cmd == h.get("command", "") for h in matcher.get("hooks", []))
            for matcher in existing_matchers
        )
        if not already_registered:
            existing_matchers.extend(pkm_matchers)
        existing_hooks[event] = existing_matchers
    return existing_hooks


def _setup_claude_code_hooks(dry_run: bool) -> None:
    """Append pkm hooks to ~/.claude/settings.json (non-destructive)."""
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    pkm_hooks = {
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "pkm hook run session-start --format system-reminder",
                    }
                ]
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "pkm hook run turn-start --format system-reminder",
                    }
                ]
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "pkm hook run turn-end --format system-reminder",
                    }
                ]
            }
        ],
    }

    existing_hooks = existing.get("hooks", {})
    merged = _merge_claude_hooks(existing_hooks, pkm_hooks)
    merged_config = json.dumps({"hooks": merged}, indent=2)

    if dry_run:
        click.echo(
            "# Claude Code hooks configuration (appended to ~/.claude/settings.json):"
        )
        click.echo(merged_config)
        return

    existing["hooks"] = merged
    import os
    import stat

    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    os.chmod(settings_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 owner-only
    click.echo(f"Wrote hooks to {settings_path}")


def _setup_codex_hooks(dry_run: bool) -> None:
    """Print or append Codex CLI hook configuration."""
    # Use existing tomllib compat pattern
    try:
        import tomllib as _tomllib  # noqa: F401
    except ImportError:
        pass

    config_text = (
        "# Add to ~/.codex/config.toml:\n"
        "[hooks]\n"
        'session_start = "pkm hook run session-start --format system-reminder"\n'
        'user_prompt_submit = "pkm hook run turn-start --format system-reminder"\n'
        'stop = "pkm hook run turn-end --format system-reminder"\n'
    )
    if dry_run:
        click.echo(config_text)
        return
    click.echo("Add the following to ~/.codex/config.toml:")
    click.echo(config_text)
