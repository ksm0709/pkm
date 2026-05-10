import asyncio
import contextvars
import sys
import json
import os
import logging
import re
import socket
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Dict, Any, Optional, List

from pkm.credential_store import agent_credential_env

# Configure logging to stderr so it doesn't interfere with stdout IPC
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pkm.worker")

_ASK_AGENT_CACHE_MAX = 16
_ASK_AGENT_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_SESSION_ID_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def sync_task_api_keys(env_keys: Optional[Dict[str, str]]) -> None:
    """Make LLM provider keys match the current task request, not daemon startup."""
    if env_keys is None:
        return

    clean_env_keys = {
        k: v for k, v in env_keys.items() if not k.endswith("_API_KEY") or v.strip()
    }
    requested_api_keys = {k for k in clean_env_keys if k.endswith("_API_KEY")}
    for key in list(os.environ):
        if key.endswith("_API_KEY") and key not in requested_api_keys:
            os.environ.pop(key, None)
    os.environ.update(clean_env_keys)


@dataclass
class AgentTaskOutcome:
    status: str
    response: str = ""
    result_summary: str = ""
    error: str | None = None


def reasoning_kwargs(model: str, effort: str | None) -> dict[str, Any]:
    """Translate reasoning_effort to model-compatible litellm kwargs.

    When adding a new model or provider, check the parameter name at:
    https://docs.litellm.ai/docs/providers
    """
    if not effort:
        return {}

    normalized_model = model.split("/", 1)[-1].lower()

    # Gemini 3+ uses thinking_level (low/high)
    if "gemini-3" in normalized_model:
        level = "high" if effort in {"medium", "high", "xhigh"} else "low"
        return {"thinking_level": level}

    # Gemini 2.5: litellm maps reasoning_effort to thinking budget_tokens natively.
    if "gemini-2.5" in normalized_model:
        return {"reasoning_effort": effort}

    # Anthropic Claude 3.7+/4+ and OpenAI reasoning models accept reasoning_effort.
    if "claude-3-7" in normalized_model or "claude-4" in normalized_model:
        return {"reasoning_effort": effort}
    if normalized_model.startswith(("o1", "o3", "o4", "gpt-5")):
        return {"reasoning_effort": effort}

    return {}


def redact(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: (
                "<REDACTED>"
                if "key" in k.lower() or "token" in k.lower()
                else redact(v)
            )
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [redact(i) for i in data]
    return data


def _agent_session_id(
    session_prefix: str, task_id: str, persistent_session_id: Optional[str] = None
) -> str:
    if not persistent_session_id:
        return f"{session_prefix}-{task_id}"
    suffix = _SESSION_ID_SAFE.sub("-", persistent_session_id).strip(".-")
    if not suffix:
        return f"{session_prefix}-{task_id}"
    return f"{session_prefix}-{suffix[:160]}"


def _cached_agent(cache_key: str, signature: tuple[Any, ...]) -> Any | None:
    cached = _ASK_AGENT_CACHE.get(cache_key)
    if not cached or cached.get("signature") != signature:
        if cached:
            _ASK_AGENT_CACHE.pop(cache_key, None)
        return None
    if hasattr(_ASK_AGENT_CACHE, "move_to_end"):
        _ASK_AGENT_CACHE.move_to_end(cache_key)
    return cached.get("agent")


def _store_agent(cache_key: str, signature: tuple[Any, ...], agent: Any) -> None:
    _ASK_AGENT_CACHE[cache_key] = {"signature": signature, "agent": agent}
    if hasattr(_ASK_AGENT_CACHE, "move_to_end"):
        _ASK_AGENT_CACHE.move_to_end(cache_key)
    while len(_ASK_AGENT_CACHE) > _ASK_AGENT_CACHE_MAX:
        if hasattr(_ASK_AGENT_CACHE, "popitem"):
            try:
                _ASK_AGENT_CACHE.popitem(last=False)
                continue
            except TypeError:
                pass
        oldest = next(iter(_ASK_AGENT_CACHE))
        _ASK_AGENT_CACHE.pop(oldest, None)


def _stringify_turn_stop_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output", "summary", "content", "text", "result"):
            if key in value:
                rendered = _stringify_turn_stop_result(value[key])
                if rendered:
                    return rendered
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)
    return str(value)


def _turn_stop_summary_from_chunk(chunk: dict[str, Any]) -> str:
    if chunk.get("type") != "tool_end" or chunk.get("name") != "turn_stop":
        return ""
    for key in ("result", "content", "output"):
        rendered = _stringify_turn_stop_result(chunk.get(key))
        if rendered:
            return rendered
    return ""


class IPCClient:
    def __init__(self):
        self._abort_event = None

    @property
    def abort_event(self):
        if self._abort_event is None:
            self._abort_event = asyncio.Event()
        return self._abort_event

    @property
    def loop(self):
        return asyncio.get_running_loop()

    async def send_message(self, msg: Dict[str, Any]):
        def _write():
            sys.stdout.write(json.dumps(msg) + "\n")
            sys.stdout.flush()

        await self.loop.run_in_executor(None, _write)

    async def reader_loop(self):
        while True:

            def _read():
                return sys.stdin.readline()

            line = await self.loop.run_in_executor(None, _read)
            if not line:
                break
            try:
                msg = json.loads(line)
                msg_type = msg.get("type")

                if msg_type == "abort":
                    logger.info("Received abort signal from daemon")
                    self.abort_event.set()
                elif msg_type == "task":
                    logger.info(f"Received task: {msg.get('id')}")
                    asyncio.create_task(handle_task(msg))
                else:
                    logger.warning(f"Unexpected message type: {msg_type}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON: {e}")
            except Exception as e:
                logger.error(f"Error in reader loop: {e}")


ipc = IPCClient()
_ENV_LOCK = asyncio.Lock()
_ENV_LOCK_HELD: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pkm_worker_env_lock_held", default=False
)


async def _run_agent_task(
    task_id: str,
    session_prefix: str,
    user_content: str,
    system_prompt: str,
    vault_dir: str,
    model: Optional[str] = None,
    model_candidates: Optional[List[str]] = None,
    env_keys: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    cwd: Optional[str] = None,
    skills_dirs: Optional[List[str]] = None,
    persistent_session_id: Optional[str] = None,
    mock_response_prefix: str = "Mocked response for:",
):
    async def run() -> AgentTaskOutcome:
        return await _run_agent_task_impl(
            task_id=task_id,
            session_prefix=session_prefix,
            user_content=user_content,
            system_prompt=system_prompt,
            vault_dir=vault_dir,
            model=model,
            model_candidates=model_candidates,
            reasoning_effort=reasoning_effort,
            cwd=cwd,
            skills_dirs=skills_dirs,
            persistent_session_id=persistent_session_id,
            mock_response_prefix=mock_response_prefix,
        )

    return await _run_with_env(env_keys or {}, run)


async def _run_with_env(
    env_vars: Dict[str, str],
    action: Callable[[], Awaitable[Any]],
) -> Any:
    if _ENV_LOCK_HELD.get():
        return await _run_with_env_unlocked(env_vars, action)

    async with _ENV_LOCK:
        token = _ENV_LOCK_HELD.set(True)
        try:
            return await _run_with_env_unlocked(env_vars, action)
        finally:
            _ENV_LOCK_HELD.reset(token)


async def _run_with_env_unlocked(
    env_vars: Dict[str, str],
    action: Callable[[], Awaitable[Any]],
) -> Any:
    previous_env = {key: os.environ.get(key) for key in env_vars}
    try:
        os.environ.update(env_vars)
        return await action()
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def _run_agent_task_impl(
    task_id: str,
    session_prefix: str,
    user_content: str,
    system_prompt: str,
    vault_dir: str,
    model: Optional[str] = None,
    model_candidates: Optional[List[str]] = None,
    reasoning_effort: Optional[str] = None,
    cwd: Optional[str] = None,
    skills_dirs: Optional[List[str]] = None,
    persistent_session_id: Optional[str] = None,
    mock_response_prefix: str = "Mocked response for:",
):
    try:
        if os.environ.get("PKM_TEST_MOCK_LLM") == "1":
            if mock_response_prefix == "Mocked maintenance response":
                mock_res = mock_response_prefix
            else:
                mock_res = f"{mock_response_prefix} {user_content}"
            await ipc.send_message(
                {
                    "type": "result",
                    "id": task_id,
                    "status": "success",
                    "data": {"response": mock_res},
                }
            )
            return AgentTaskOutcome(
                status="success",
                response=mock_res,
                result_summary=mock_res,
            )

        from tiny_agent.agent import Agent
        from pkm.tools import get_pkm_tools

        ipc.abort_event.clear()

        models_to_try = [m for m in (model_candidates or []) if m]
        if not models_to_try:
            models_to_try = [model] if model and model != "auto" else []
        if not models_to_try:
            try:
                from pkm.models import resolve_auto_models

                models_to_try = resolve_auto_models()
            except ImportError:
                models_to_try = ["gemini/gemini-3-flash-preview"]

        if not models_to_try:
            raise RuntimeError("No API keys found for any supported models.")

        tools = get_pkm_tools()

        async def on_tool_start(name, arguments, agent_ref):
            await ipc.send_message(
                {
                    "type": "stream",
                    "id": task_id,
                    "chunk": {
                        "type": "tool_detail",
                        "name": name,
                        "arguments": arguments,
                    },
                }
            )

        instruction_dirs = [vault_dir]
        if cwd and cwd not in instruction_dirs:
            instruction_dirs.append(cwd)

        model_errors: list[str] = []
        for resolved_model in models_to_try:
            try:
                litellm_kwargs = reasoning_kwargs(resolved_model, reasoning_effort)
                agent_session_id = _agent_session_id(
                    session_prefix, task_id, persistent_session_id
                )
                agent_signature = (
                    resolved_model,
                    system_prompt,
                    vault_dir,
                    tuple(instruction_dirs),
                    tuple(skills_dirs or []),
                    json.dumps(litellm_kwargs, sort_keys=True, default=str),
                )
                agent = (
                    _cached_agent(agent_session_id, agent_signature)
                    if persistent_session_id
                    else None
                )
                if agent is None:
                    agent = Agent(
                        session_id=agent_session_id,
                        model=resolved_model,
                        system_prompt=system_prompt,
                        tools=tools,
                        skills_dirs=skills_dirs or [],
                        instruction_dirs=instruction_dirs,
                        max_iterations=1000,
                        hooks={"on_tool_start": on_tool_start},
                        litellm_kwargs=litellm_kwargs,
                        load_builtin_tools=False,
                    )
                    if persistent_session_id:
                        _store_agent(agent_session_id, agent_signature, agent)
                else:
                    # The hook captures the current task id, so refresh it for reused sessions.
                    agent.hooks = {"on_tool_start": on_tool_start}
                if persistent_session_id and hasattr(agent, "tasks"):
                    # Conversation memory persists across web asks; per-turn plans should not.
                    agent.tasks = []

                response_chunks = []
                turn_stop_summary = ""

                async def run_agent():
                    nonlocal turn_stop_summary
                    async for chunk in agent.run(user_content):
                        await ipc.send_message(
                            {"type": "stream", "id": task_id, "chunk": chunk}
                        )

                        if chunk.get("type") == "content":
                            content = chunk.get("content", "")
                            response_chunks.append(content)
                        elif chunk.get("type") == "tool_end":
                            summary = _turn_stop_summary_from_chunk(chunk)
                            if summary:
                                turn_stop_summary = summary
                        elif chunk.get("type") == "error":
                            raise RuntimeError(chunk.get("content"))

                agent_task = asyncio.create_task(run_agent())
                abort_task = asyncio.create_task(ipc.abort_event.wait())

                done, pending = await asyncio.wait(
                    [agent_task, abort_task], return_when=asyncio.FIRST_COMPLETED
                )

                if abort_task in done:
                    agent_task.cancel()
                    try:
                        await agent_task
                    except asyncio.CancelledError:
                        pass
                    raise RuntimeError("Task aborted by daemon")

                if agent_task in done:
                    abort_task.cancel()
                    exc = agent_task.exception()
                    if exc:
                        raise exc

                full_response = "".join(response_chunks)
                result_summary = turn_stop_summary or full_response

                await ipc.send_message(
                    {
                        "type": "result",
                        "id": task_id,
                        "status": "success",
                        "data": {"response": full_response},
                    }
                )
                return AgentTaskOutcome(
                    status="success",
                    response=full_response,
                    result_summary=result_summary,
                )
            except Exception as e:
                if str(e) == "Task aborted by daemon":
                    raise
                model_errors.append(f"{resolved_model}: {e}")
                logger.warning(
                    "Model %s failed; trying next configured candidate",
                    resolved_model,
                )

        raise RuntimeError(
            "All configured LLM model candidates failed: " + "; ".join(model_errors)
        )
    except Exception as e:
        await ipc.send_message({"type": "error", "id": task_id, "message": str(e)})
        return AgentTaskOutcome(status="failure", error=str(e))


async def handle_ask(
    task_id: str,
    query: str,
    context: str,
    vault_dir: str,
    model: Optional[str] = None,
    model_candidates: Optional[List[str]] = None,
    env_keys: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    cwd: Optional[str] = None,
    ask_session_id: Optional[str] = None,
):
    system_prompt = (
        "You are an autonomous PKM agent with direct access to the user's vault via the following tools:\n"
        "- read_daily_log(date_str): read a daily note\n"
        "- add_daily_log(text): append to today's daily note\n"
        "- read_note(note_id): read an atomic note\n"
        "- search_notes(query): search notes by title substring\n"
        "- semantic_search(query, top, memory_type, min_importance): semantic similarity search\n"
        "- add_note(title, content, tags, memory_type, importance): create a new atomic note\n"
        "- update_note(note_id, content, tags): update an existing note\n"
        "- rename_note(old_note_id, new_note_id): rename a note and rewrite backlinks\n"
        "- get_graph_context(note_id, depth): get wikilink graph (requires daemon; depth>1 or outbound)\n"
        "- vault_stats(): vault health snapshot (note/orphan/tag counts, index status)\n"
        "- list_stale_notes(days): notes not modified in last N days\n"
        "- list_orphans(): notes with zero inbound AND outbound links\n"
        "- list_malformed_notes(): notes with duplicated or invalid leading frontmatter\n"
        "- find_backlinks_for_note(note_id): inbound links to a note (daemon-free fallback)\n"
        "- list_tags(): all tags with counts; call before tag_search to discover tag names\n"
        "- tag_search(pattern): filter by tag (exact/glob/AND+/OR,) — NOT for content queries\n"
        "- list_consolidation_candidates(): daily notes ready for zettelkasten distillation\n"
        "- mark_consolidated(date_str, distilled_note_ids): mark daily as consolidated (requires proof)\n"
        "- read_recent_note_activity(tail): last N entries from operation log (best-effort)\n"
        "Tool selection: use search_notes for title match, semantic_search for meaning, tag_search for topic.\n"
        "ALWAYS use these tools directly to interact with the vault — never use shell commands.\n"
        "When asked to execute a workflow (e.g. zettelkasten maintenance), call `load_skill` with the appropriate skill ID "
        "to get full instructions, then execute every step by calling the vault tools listed above.\n"
        "Always complete the requested action — do not just describe what you would do."
    )
    user_content = (
        "Conversation history supplied by the web ask client:\n"
        f"{context}\n\n"
        "Answer the current query using the conversation history above when relevant.\n"
        f"Current query: {query}"
        if context
        else query
    )

    await _run_agent_task(
        task_id=task_id,
        session_prefix="pkm-ask",
        user_content=user_content,
        system_prompt=system_prompt,
        vault_dir=vault_dir,
        model=model,
        model_candidates=model_candidates,
        env_keys=env_keys,
        reasoning_effort=reasoning_effort,
        cwd=cwd,
        skills_dirs=[os.path.expanduser("~/.agents/skills/pkm")],
        persistent_session_id=ask_session_id,
        mock_response_prefix="Mocked response for:",
    )


async def _dispatch_workflow(
    task_id: str,
    workflow_id: str,
    vault_dir: str,
    model: Optional[str] = None,
    env_keys: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    cwd: Optional[str] = None,
    source: str = "unknown",
):
    from pathlib import Path
    from pkm.config import VaultConfig
    from pkm.workflows import load_workflows, resolve_hook
    from pkm.workflows.history import append_workflow_history

    def record_history(
        *,
        status: str,
        phase: str,
        error: str | None = None,
        result_summary: str = "",
    ) -> None:
        append_workflow_history(
            vault_dir,
            {
                "workflow_id": workflow_id,
                "task_id": task_id,
                "hostname": socket.gethostname(),
                "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": status,
                "source": source or "unknown",
                "phase": phase,
                "error": error,
                "result_summary": result_summary,
            },
        )

    configs = load_workflows(vault_path=vault_dir)
    config_map = {c.id: c for c in configs}
    config = config_map.get(workflow_id)
    if config is None:
        message = f"Unknown workflow_id: {workflow_id}"
        await ipc.send_message(
            {
                "type": "error",
                "id": task_id,
                "message": message,
            }
        )
        record_history(status="failure", phase="load", error=message)
        return

    vault = VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))
    today = str(date.today())

    try:
        pre_fn = resolve_hook(config.pre_hook)
        if pre_fn is not None:
            hook_result = pre_fn(vault, today)
            system_prompt = config.system_prompt_template.format(**hook_result)
        else:
            system_prompt = config.system_prompt_template
    except Exception as exc:
        message = str(exc)
        await ipc.send_message({"type": "error", "id": task_id, "message": message})
        record_history(status="failure", phase="pre_hook", error=message)
        return

    user_content = f"Execute the {workflow_id} workflow now."

    outcome = await _run_agent_task(
        task_id=task_id,
        session_prefix=f"pkm-{workflow_id}",
        user_content=user_content,
        system_prompt=system_prompt,
        vault_dir=vault_dir,
        model=model,
        env_keys=env_keys,
        reasoning_effort=reasoning_effort,
        cwd=cwd,
        mock_response_prefix=f"Mocked {workflow_id} response",
    )
    if outcome is None:
        outcome = AgentTaskOutcome(status="success")

    if outcome.status != "success":
        record_history(
            status="failure",
            phase="agent",
            error=outcome.error,
            result_summary=outcome.result_summary,
        )
        return

    try:
        post_fn = resolve_hook(config.post_hook)
        if post_fn is not None:
            post_fn(vault, None)
    except Exception as exc:
        message = str(exc)
        await ipc.send_message({"type": "error", "id": task_id, "message": message})
        record_history(
            status="failure",
            phase="post_hook",
            error=message,
            result_summary=outcome.result_summary,
        )
        return

    record_history(
        status="success",
        phase="complete",
        result_summary=outcome.result_summary,
    )


async def handle_task(msg: Dict[str, Any]):
    env_vars = msg.get("env", {})

    async def run() -> None:
        await _handle_task_with_current_env(msg)

    await _run_with_env(env_vars, run)


async def _handle_task_with_current_env(msg: Dict[str, Any]) -> None:
    task_id = str(msg.get("id", ""))
    task_type = msg.get("task_type")

    vault_dir = os.environ.get("PKM_VAULT_DIR", ".")

    from pkm.sandbox import setup_sandbox

    setup_sandbox(vault_dir)

    if task_type == "ask":
        env_keys = msg.get("env_keys")
        if not isinstance(env_keys, dict) or not env_keys:
            env_keys = agent_credential_env()
        await handle_ask(
            task_id,
            msg.get("query", ""),
            msg.get("context", ""),
            vault_dir,
            msg.get("model"),
            msg.get("model_candidates"),
            env_keys,
            msg.get("reasoning_effort"),
            msg.get("cwd"),
            msg.get("ask_session_id"),
        )
    elif task_type == "workflow":
        env_keys = msg.get("env_keys")
        if not isinstance(env_keys, dict) or not env_keys:
            env_keys = agent_credential_env()
        await _dispatch_workflow(
            task_id,
            msg.get("workflow_id", ""),
            vault_dir,
            msg.get("model"),
            env_keys,
            msg.get("reasoning_effort"),
            msg.get("cwd"),
            msg.get("workflow_source", "unknown"),
        )
    else:
        await ipc.send_message(
            {
                "type": "error",
                "id": task_id,
                "message": f"Unknown task type: {task_type}",
            }
        )


async def main():
    logger.info("PKM LLM Worker started")

    vault_dir = os.environ.get("PKM_VAULT_DIR", ".")
    try:
        os.chdir(vault_dir)
        from pkm.sandbox import setup_sandbox

        setup_sandbox(vault_dir)
        logger.info(f"Sandbox initialized for vault: {vault_dir}")
    except Exception as e:
        logger.error(f"Failed to initialize sandbox: {e}")
        sys.exit(1)

    await ipc.reader_loop()


if __name__ == "__main__":
    asyncio.run(main())
