"""pkm hook command group — lifecycle hooks for LLM agent tool integrations."""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import click


from typing import Any


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


def _get_note_desc(result) -> str:
    """Extract a short description from a search result's note file."""
    try:
        from pkm.frontmatter import parse as parse_note

        note = parse_note(Path(result.path))
        desc = note.meta.get("description")
        if desc:
            return str(desc)[:60]
        body = note.body.strip()
        if body:
            return body[:60]
    except Exception:
        pass
    return ""


def _load_hook_config(vault) -> dict[str, Any]:
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


def _is_debug_mode(vault) -> bool:
    """Return True if hooks.debug = true in .pkm/config.toml."""
    try:
        config = _load_hook_config(vault)
        return bool(config.get("hooks", {}).get("debug", False))
    except Exception:
        return False


def _write_hooks_debug(vault, enabled: bool) -> None:
    """Set hooks.debug in .pkm/config.toml (creates file if missing)."""
    config_path = vault.pkm_dir / "config.toml"
    vault.pkm_dir.mkdir(parents=True, exist_ok=True)

    # Read existing content as raw text to preserve other settings
    lines: list[str] = []
    if config_path.exists():
        lines = config_path.read_text(encoding="utf-8").splitlines()

    # Find [hooks] section and debug key
    in_hooks = False
    hooks_idx = -1
    debug_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[hooks]":
            in_hooks = True
            hooks_idx = i
        elif stripped.startswith("[") and stripped != "[hooks]":
            in_hooks = False
        elif in_hooks and stripped.startswith("debug"):
            debug_idx = i

    value_str = "true" if enabled else "false"
    new_line = f"debug = {value_str}"

    if debug_idx != -1:
        lines[debug_idx] = new_line
    elif hooks_idx != -1:
        lines.insert(hooks_idx + 1, new_line)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("[hooks]")
        lines.append(new_line)

    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_session_state(vault) -> dict[str, Any]:
    """Load .pkm/session_state.json. Returns defaults on missing or corrupt."""
    defaults: dict[str, Any] = {"session_count": 0, "last_consolidation_at": None}
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


def _save_session_state(vault, state: dict[str, Any]) -> None:
    """Write .pkm/session_state.json."""
    try:
        vault.pkm_dir.mkdir(parents=True, exist_ok=True)
        state_path = vault.pkm_dir / "session_state.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _check_consolidation_trigger(vault, config: dict[str, Any]) -> str | None:
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

    # 1. Zettel-pending signal (daemon auto-consolidated dailies)
    try:
        zettel_signal = vault.pkm_dir / "zettel-pending"
        if zettel_signal.exists():
            import json as _json

            sig = _json.loads(zettel_signal.read_text(encoding="utf-8"))
            marked = sig.get("marked", 0)
            lines.append("## Zettel Loop Ready")
            lines.append(
                f"Daemon auto-consolidated {marked} daily note(s) on shutdown. "
                "Run `/pkm:zettel-loop` to distill into permanent knowledge."
            )
            lines.append("")
            zettel_signal.unlink()
    except Exception:
        pass

    # 2. Consolidation trigger (conditional)
    try:
        hook_config = _load_hook_config(vault)
        trigger_msg = _check_consolidation_trigger(vault, hook_config)
        if trigger_msg:
            lines.append("## Consolidation Recommended")
            lines.append(trigger_msg)
            lines.append("")
    except Exception:
        pass

    # 2. PKM command reference — single source of truth
    lines.extend(
        [
            "## PKM",
            '`pkm daily add "<text>"` — log decisions, findings, code changes',
            '`pkm daily add --sub "<title>"` — create linked sub-note + log [[wikilink]] in today\'s daily',
            '`pkm search "<query>"` — recall related notes',
            '`pkm note add --content "<insight>" --type semantic --importance 7 --tags tag1,tag2` — atomic note',
            "`pkm data add <fname> <path-or-url>` — copy local file or download URL into vault data/",
            "`pkm data rm <fname>` — remove a data file from vault",
            "For detailed workflows and usage: `/pkm` skill",
        ]
    )

    # 3. Recent work context from daily notes
    from datetime import date, timedelta

    daily_dir = vault.daily_dir
    daily_lines: list[str] = []
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
                daily_lines.append(f"### {d}\n{preview}")
                if len(daily_lines) >= 2:
                    break

    if daily_lines:
        lines.append("")
        lines.append("## Recent Work Context")
        lines.extend(daily_lines)

    content = "\n".join(lines).strip()

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
                    text = text[end + 3 :].strip()
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
        from pkm.search_engine import (
            load_index,
            search as engine_search,
            search_via_daemon,
        )

        results = search_via_daemon(query, vault, top_n=3, min_importance=5.0)
        if results is None:
            index = load_index(vault)
            results = engine_search(query, index, top_n=3, min_importance=5.0)

        if results:
            lines.append("## Relevant Notes")
            for r in results:
                mt = r.memory_type or "semantic"
                desc = _get_note_desc(r)
                suffix = f" — {desc}" if desc else ""
                lines.append(f"- [{mt}|imp:{r.importance:.0f}] {r.title}{suffix}")
            lines.append("")
    except Exception:
        pass

    if session_id:
        lines.append(f"Session: {session_id}")
    lines.append('`pkm search "<query>"` — recall related notes if needed'
                 '\nFor full command reference see the `/pkm` skill or session-start context.')

    content = "\n".join(lines)
    if output_format == "system-reminder":
        click.echo(f"<system-reminder>\n{content}\n</system-reminder>")
    else:
        click.echo(content)


def _handle_turn_end(
    ctx, session_id: str | None, summary: str | None, output_format: str, **_ignored
) -> None:
    # Always emit preservation guide (meta-instruction only; command details in session-start)
    guide = "Save key learnings from this session with pkm before stopping. See /pkm skill for commands."
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
            raise RuntimeError(
                "Resolved daily path escapes daily_dir — aborting write."
            )
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
    payload: dict[str, Any] = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read(65536)
            payload = json.loads(raw)
        except Exception:
            pass

    if payload.get("stop_hook_active", False):
        sys.exit(0)

    instructions = """\
KNOWLEDGE EXTRACTION: Save key learnings from this session using pkm commands.
Be selective — skip trivial facts. See /pkm skill for available commands. Then you may stop."""

    hook_source = payload.get("hook_source", "")

    transcript_path = payload.get("transcript_path", "")
    if not transcript_path and hook_source != "opencode-plugin":
        # No stdin payload (e.g. called from sidecar daemon) — emit instructions
        # to stdout so the caller can inject them, then exit 0.
        click.echo(f"[pkm hook run turn-end-exit2]: {instructions}")
        sys.exit(0)

    if hook_source == "opencode-plugin":
        print(
            json.dumps(
                {
                    "decision": "block",
                    "inject_prompt": instructions,
                    "stop_hook_active": True,
                }
            )
        )
        sys.exit(0)
    else:
        print(instructions, file=sys.stderr)
        sys.exit(2)


def _is_pkm_hook(hook_entry: dict[str, Any]) -> bool:
    cmd = hook_entry.get("command", "")
    prompt = hook_entry.get("prompt", "")
    return (
        "pkm hook run" in cmd
        or "pkm agent hook" in cmd
        or "PKM" in prompt
        or "codex/hooks/stop.sh" in cmd
    )


def _handle_remove(dry_run: bool) -> None:
    """Remove PKM hooks from ~/.claude/settings.json, keep all other hooks."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        click.echo("~/.claude/settings.json not found — nothing to remove.")
        return

    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as e:
        click.echo(f"Error reading settings.json: {e}", err=True)
        return

    hooks = existing.get("hooks", {})
    removed_counts: dict[str, int] = {}

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
    # Vault-free group: lazy-load vault for run subcommands that need it.
    if "vault" not in ctx.obj or ctx.obj["vault"] is None:
        from pkm.config import get_vault as _get_vault

        try:
            ctx.obj["vault"] = _get_vault(None)
        except Exception:
            ctx.obj["vault"] = None

    # Debug mode override: if hooks.debug = true in config, use plain format
    if ctx.obj.get("vault") is not None and _is_debug_mode(ctx.obj["vault"]):
        output_format = "plain"

    if hook_name == "session-start":
        _handle_session_start(ctx, output_format=output_format, top=top)
    elif hook_name == "turn-start":
        _handle_turn_start(ctx, output_format=output_format, session_id=session_id)
    elif hook_name == "turn-end":
        _handle_turn_end(
            ctx, session_id=session_id, summary=summary, output_format=output_format
        )
    elif hook_name == "turn-end-exit2":
        _handle_turn_end_exit2(ctx)


@hook.command(name="setup")
@click.option("--tool", type=click.Choice(["claude-code", "codex"]), default=None)
@click.option("--dry-run", is_flag=True, help="Print config without writing")
@click.pass_context
def setup(ctx: click.Context, tool: str | None, dry_run: bool) -> None:
    """Print hook install instructions for agent tools.

    Without --tool, sets up all supported agents (claude-code and codex).
    Use --tool to set up a specific agent only.
    """
    if tool is None or tool == "claude-code":
        _setup_claude_code_hooks(dry_run)
    if tool is None:
        click.echo("")
        click.echo("─" * 60)
        click.echo("")
    if tool is None or tool == "codex":
        _setup_codex_hooks(dry_run)


@hook.command(name="remove")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be removed without writing"
)
@click.pass_context
def remove(ctx: click.Context, dry_run: bool) -> None:
    """Remove PKM hooks from ~/.claude/settings.json.

    Removes hook entries added by 'pkm hook setup --tool claude-code'.
    Keeps all other hooks (OMC, TypeScript LSP, etc.) intact.
    """
    _handle_remove(dry_run)


@hook.command(name="migrate", hidden=True)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def migrate(ctx: click.Context, dry_run: bool) -> None:
    """Deprecated: use 'pkm hook remove' instead."""
    click.echo(
        "Note: 'pkm hook migrate' is deprecated, use 'pkm hook remove'", err=True
    )
    _handle_remove(dry_run)


@hook.command(name="debug")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.pass_context
def debug_cmd(ctx: click.Context, state: str) -> None:
    """Toggle hook debug mode.

    on  — injected messages shown as plain text (visible in terminal)\n
    off — injected messages wrapped in <system-reminder> (default, hidden from user)
    """
    if "vault" not in ctx.obj or ctx.obj["vault"] is None:
        from pkm.config import get_vault as _get_vault

        try:
            ctx.obj["vault"] = _get_vault(None)
        except Exception:
            click.echo("Error: no active vault found.", err=True)
            return

    vault = ctx.obj["vault"]
    enabled = state == "on"
    _write_hooks_debug(vault, enabled)
    status = (
        "ON (messages visible as plain text)"
        if enabled
        else "OFF (messages hidden in system-reminder)"
    )
    click.echo(f"Hook debug mode: {status}")
    click.echo(f"  Config: {vault.pkm_dir / 'config.toml'}")


_PKM_HOOKS: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "pkm hook run session-start --format system-reminder",
                    "timeout": 10,
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
                    "timeout": 10,
                }
            ]
        }
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "pkm hook run turn-end-exit2",
                    "timeout": 30,
                }
            ]
        }
    ],
}


def _setup_claude_code_hooks(dry_run: bool) -> None:
    """Merge PKM hooks into ~/.claude/settings.json."""
    import os
    import stat

    settings_path = Path.home() / ".claude" / "settings.json"

    click.echo("PKM Claude Code hooks — install to ~/.claude/settings.json")

    try:
        existing = (
            json.loads(settings_path.read_text(encoding="utf-8"))
            if settings_path.exists()
            else {}
        )
    except Exception as e:
        click.echo(f"Error reading settings.json: {e}", err=True)
        return

    hooks = existing.setdefault("hooks", {})

    added: list[str] = []
    skipped: list[str] = []

    for event, matchers in _PKM_HOOKS.items():
        event_hooks = hooks.setdefault(event, [])
        # Check if PKM hook already present for this event
        all_hook_entries = [h for m in event_hooks for h in m.get("hooks", [])]
        if any(_is_pkm_hook(h) for h in all_hook_entries):
            skipped.append(event)
            continue
        event_hooks.extend(matchers)
        added.append(event)

    for event in added:
        click.echo(f"  Added hook: {event}")
    for event in skipped:
        click.echo(f"  Already installed: {event} (skipped)")

    if not added:
        click.echo("All PKM hooks already present — nothing to do.")
        return

    if dry_run:
        click.echo("Dry run — no changes written.")
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    os.chmod(settings_path, stat.S_IRUSR | stat.S_IWUSR)
    click.echo(f"  Written: {settings_path}")
    click.echo("")
    click.echo("Done. Restart Claude Code to activate PKM hooks.")
    click.echo("To remove: pkm hook remove")


def _setup_codex_hooks(dry_run: bool) -> None:
    """Merge PKM hooks into ~/.codex/hooks.json."""
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[4]
    codex_hooks_src = repo_root / "codex" / "hooks.json"
    codex_hooks_dst = Path.home() / ".codex" / "hooks.json"

    click.echo("PKM Codex hooks — install to ~/.codex/hooks.json")

    try:
        pkm_hooks_data = json.loads(codex_hooks_src.read_text(encoding="utf-8"))
    except Exception as e:
        click.echo(f"Error reading PKM codex hooks: {e}", err=True)
        return

    # Replace stop.sh placeholder path with actual repo path
    stop_sh = str(repo_root / "codex" / "hooks" / "stop.sh")
    pkm_hooks = pkm_hooks_data.get("hooks", {})
    for event_list in pkm_hooks.values():
        for matcher in event_list:
            for hook in matcher.get("hooks", []):
                cmd = hook.get("command", "")
                if "/path/to/pkm/codex/hooks/stop.sh" in cmd:
                    hook["command"] = f"bash {stop_sh}"

    try:
        existing = (
            json.loads(codex_hooks_dst.read_text(encoding="utf-8"))
            if codex_hooks_dst.exists()
            else {}
        )
    except Exception as e:
        click.echo(f"Error reading ~/.codex/hooks.json: {e}", err=True)
        return

    hooks = existing.setdefault("hooks", {})

    added: list[str] = []
    skipped: list[str] = []

    for event, matchers in pkm_hooks.items():
        event_hooks = hooks.setdefault(event, [])
        all_hook_entries = [h for m in event_hooks for h in m.get("hooks", [])]
        if any(_is_pkm_hook(h) for h in all_hook_entries):
            skipped.append(event)
            continue
        event_hooks.extend(matchers)
        added.append(event)

    for event in added:
        click.echo(f"  Added hook: {event}")
    for event in skipped:
        click.echo(f"  Already installed: {event} (skipped)")

    if not added:
        click.echo("All PKM hooks already present — nothing to do.")
        return

    if dry_run:
        click.echo("Dry run — no changes written.")
        return

    codex_hooks_dst.parent.mkdir(parents=True, exist_ok=True)
    codex_hooks_dst.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    click.echo(f"  Written: {codex_hooks_dst}")
    click.echo("")
    click.echo("Done. Restart Codex to activate PKM hooks.")
