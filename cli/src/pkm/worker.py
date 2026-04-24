import asyncio
import sys
import json
import os
import logging
from typing import Dict, Any, Optional, List

# Configure logging to stderr so it doesn't interfere with stdout IPC
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pkm.worker")


def reasoning_kwargs(model: str, effort: str | None) -> dict[str, Any]:
    """Translate reasoning_effort to model-compatible litellm kwargs.

    When adding a new model or provider, check the parameter name at:
    https://docs.litellm.ai/docs/providers
    """
    if not effort:
        return {}
    # Gemini 3+ uses thinking_level (low/high)
    if "gemini-3" in model:
        level = "high" if effort in {"medium", "high", "xhigh"} else "low"
        return {"thinking_level": level}
    # Gemini 2.5: litellm maps reasoning_effort → thinking budget_tokens natively
    # Anthropic (claude-3-7+), OpenAI o-series: use reasoning_effort directly
    return {"reasoning_effort": effort}


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


async def _run_agent_task(
    task_id: str,
    session_prefix: str,
    user_content: str,
    system_prompt: str,
    vault_dir: str,
    model: Optional[str] = None,
    env_keys: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    cwd: Optional[str] = None,
    skills_dirs: Optional[List[str]] = None,
    mock_response_prefix: str = "Mocked response for:",
):
    if env_keys:
        os.environ.update(env_keys)

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
        return

    try:
        from tiny_agent.agent import Agent
        from pkm.tools import get_pkm_tools

        ipc.abort_event.clear()

        models_to_try = [model] if model and model != "auto" else []
        if not models_to_try:
            try:
                from pkm.models import resolve_auto_models

                models_to_try = resolve_auto_models()
            except ImportError:
                models_to_try = ["gemini/gemini-3-flash-preview"]

        if not models_to_try:
            raise RuntimeError("No API keys found for any supported models.")

        resolved_model = models_to_try[0]

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

        litellm_kwargs = reasoning_kwargs(resolved_model, reasoning_effort)

        instruction_dirs = [vault_dir]
        if cwd and cwd not in instruction_dirs:
            instruction_dirs.append(cwd)

        agent = Agent(
            session_id=f"{session_prefix}-{task_id}",
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

        response_chunks = []

        async def run_agent():
            async for chunk in agent.run(user_content):
                await ipc.send_message(
                    {"type": "stream", "id": task_id, "chunk": chunk}
                )

                if chunk.get("type") == "content":
                    content = chunk.get("content", "")
                    response_chunks.append(content)
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

        await ipc.send_message(
            {
                "type": "result",
                "id": task_id,
                "status": "success",
                "data": {"response": full_response},
            }
        )
    except Exception as e:
        await ipc.send_message({"type": "error", "id": task_id, "message": str(e)})


async def handle_ask(
    task_id: str,
    query: str,
    context: str,
    vault_dir: str,
    model: Optional[str] = None,
    env_keys: Optional[Dict[str, str]] = None,
    reasoning_effort: Optional[str] = None,
    cwd: Optional[str] = None,
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
        "- get_graph_context(note_id, depth): get wikilink graph (requires daemon; depth>1 or outbound)\n"
        "- vault_stats(): vault health snapshot (note/orphan/tag counts, index status)\n"
        "- list_stale_notes(days): notes not modified in last N days\n"
        "- list_orphans(): notes with zero inbound AND outbound links\n"
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
    user_content = f"Context:\n{context}\n\nQuery: {query}" if context else query

    await _run_agent_task(
        task_id=task_id,
        session_prefix="pkm-ask",
        user_content=user_content,
        system_prompt=system_prompt,
        vault_dir=vault_dir,
        model=model,
        env_keys=env_keys,
        reasoning_effort=reasoning_effort,
        cwd=cwd,
        skills_dirs=[os.path.expanduser("~/.agents/skills/pkm")],
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
):
    from pathlib import Path
    from pkm.config import VaultConfig
    from pkm.workflows import load_workflows, resolve_hook
    from datetime import date

    configs = load_workflows(vault_path=vault_dir)
    config_map = {c.id: c for c in configs}
    config = config_map.get(workflow_id)
    if config is None:
        await ipc.send_message(
            {
                "type": "error",
                "id": task_id,
                "message": f"Unknown workflow_id: {workflow_id}",
            }
        )
        return

    vault = VaultConfig(name=Path(vault_dir).name, path=Path(vault_dir))
    today = str(date.today())

    pre_fn = resolve_hook(config.pre_hook)
    if pre_fn is not None:
        hook_result = pre_fn(vault, today)
        system_prompt = config.system_prompt_template.format(**hook_result)
    else:
        system_prompt = config.system_prompt_template

    user_content = f"Execute the {workflow_id} workflow now."

    await _run_agent_task(
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

    post_fn = resolve_hook(config.post_hook)
    if post_fn is not None:
        post_fn(vault, None)


async def handle_task(msg: Dict[str, Any]):
    task_id = str(msg.get("id", ""))
    task_type = msg.get("task_type")

    env_vars = msg.get("env", {})
    for k, v in env_vars.items():
        os.environ[k] = v

    vault_dir = os.environ.get("PKM_VAULT_DIR", ".")

    from pkm.sandbox import setup_sandbox

    setup_sandbox(vault_dir)

    if task_type == "ask":
        await handle_ask(
            task_id,
            msg.get("query", ""),
            msg.get("context", ""),
            vault_dir,
            msg.get("model"),
            msg.get("env_keys", {}),
            msg.get("reasoning_effort"),
            msg.get("cwd"),
        )
    elif task_type == "workflow":
        await _dispatch_workflow(
            task_id,
            msg.get("workflow_id", ""),
            vault_dir,
            msg.get("model"),
            msg.get("env_keys", {}),
            msg.get("reasoning_effort"),
            msg.get("cwd"),
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
