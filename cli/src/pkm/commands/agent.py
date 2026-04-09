"""pkm agent command group — DEPRECATED. Use 'pkm hook' instead."""
from __future__ import annotations

import sys
import click


def _deprecation_warning(old_cmd: str, new_cmd: str) -> None:
    print(
        f"[pkm] DeprecationWarning: '{old_cmd}' is deprecated. "
        f"Use '{new_cmd}' instead.",
        file=sys.stderr,
    )


@click.group()
@click.pass_context
def agent(ctx: click.Context) -> None:
    """[DEPRECATED] Use 'pkm hook' instead."""


@agent.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """[DEPRECATED] Use 'pkm hook run <name>' instead."""


@hook.command(name="session-start")
@click.option("--format", "output_format", type=click.Choice(["plain", "system-reminder"]), default="plain")
@click.option("--top", default=5)
@click.pass_context
def session_start(ctx: click.Context, output_format: str, top: int) -> None:
    """[DEPRECATED] Use 'pkm hook run session-start' instead."""
    _deprecation_warning("pkm agent hook session-start", "pkm hook run session-start")
    from pkm.commands.hook import _handle_session_start
    try:
        _handle_session_start(ctx, output_format=output_format, top=top)
    except BaseException as e:
        import traceback
        print(f"[pkm hook error] {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)


@hook.command(name="turn-start")
@click.option("--format", "output_format", type=click.Choice(["plain", "system-reminder"]), default="plain")
@click.option("--session", "session_id", default=None)
@click.pass_context
def turn_start(ctx: click.Context, output_format: str, session_id: str | None) -> None:
    """[DEPRECATED] Use 'pkm hook run turn-start' instead."""
    _deprecation_warning("pkm agent hook turn-start", "pkm hook run turn-start")
    try:
        from pkm.commands.hook import _handle_turn_start
        _handle_turn_start(ctx, output_format=output_format, session_id=session_id)
    except BaseException as e:
        import traceback
        print(f"[pkm hook error] {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)


@hook.command(name="turn-end")
@click.option("--session", "session_id", default=None)
@click.option("--summary", default=None)
@click.pass_context
def turn_end(ctx: click.Context, session_id: str | None, summary: str | None) -> None:
    """[DEPRECATED] Use 'pkm hook run turn-end' instead."""
    _deprecation_warning("pkm agent hook turn-end", "pkm hook run turn-end")
    try:
        from pkm.commands.hook import _handle_turn_end
        _handle_turn_end(ctx, session_id=session_id, summary=summary, output_format="plain")
    except BaseException as e:
        import traceback
        print(f"[pkm hook error] {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)


@agent.command(name="setup-hooks")
@click.option("--tool", type=click.Choice(["claude-code", "codex", "opencode"]), required=True)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def setup_hooks(ctx: click.Context, tool: str, dry_run: bool) -> None:
    """[DEPRECATED] Use 'pkm hook setup' instead."""
    _deprecation_warning("pkm agent setup-hooks", "pkm hook setup")
    from pkm.commands.hook import _setup_claude_code_hooks, _setup_codex_hooks
    if tool == "claude-code":
        _setup_claude_code_hooks(dry_run)
    elif tool == "codex":
        _setup_codex_hooks(dry_run)
    else:
        click.echo("opencode support removed. Use 'pkm hook setup --tool codex' for Codex.", err=True)
