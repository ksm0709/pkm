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
        self.request_counter = 0
        self.pending_requests: Dict[str, asyncio.Future[Any]] = {}
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
                    continue

                if msg_type in ("llm_response", "llm_error"):
                    req_id = msg.get("id")
                    if req_id in self.pending_requests:
                        future = self.pending_requests.pop(req_id)
                        if not future.done():
                            future.set_result(msg)
                    else:
                        logger.warning(
                            f"Received response for unknown request: {req_id}"
                        )
                elif msg_type == "task":
                    logger.info(f"Received task: {msg.get('id')}")
                    # Dispatch task
                    asyncio.create_task(handle_task(msg))
                else:
                    logger.warning(f"Unexpected message type: {msg_type}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON: {e}")
            except Exception as e:
                logger.error(f"Error in reader loop: {e}")

    async def call_llm(
        self, messages: List[Dict[str, str]], model: Optional[str] = None
    ) -> str:
        self.request_counter += 1
        req_id = f"llm_req_{self.request_counter}"

        if os.environ.get("PKM_TEST_MOCK_LLM") == "1":
            return f"Mocked response for: {messages[-1]['content']}"

        models_to_try = [model] if model and model != "auto" else []
        if not models_to_try:
            try:
                from pkm.models import resolve_auto_models

                models_to_try = resolve_auto_models()
            except ImportError:
                models_to_try = []

        if not models_to_try:
            raise RuntimeError(
                "No API keys found for any supported models. Please export an API key "
                "(e.g. GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY) and restart the daemon."
            )

        last_error = None
        for current_model in models_to_try:
            req = {
                "type": "llm_request",
                "id": req_id,
                "messages": messages,
                "model": current_model,
            }

            future = self.loop.create_future()
            self.pending_requests[req_id] = future

            await self.send_message(req)

            # Wait for response or abort
            abort_task = asyncio.create_task(self.abort_event.wait())

            done, pending = await asyncio.wait(
                [future, abort_task], return_when=asyncio.FIRST_COMPLETED
            )

            if abort_task in done:
                future.cancel()
                raise RuntimeError("Aborted by daemon")

            abort_task.cancel()
            msg = future.result()

            if msg.get("type") == "llm_response":
                return msg.get("content", "")
            elif msg.get("type") == "llm_error":
                last_error = msg.get("message")
                logger.warning(f"LLM Error with model {current_model}: {last_error}")
                continue

        raise RuntimeError(f"All models failed. Last error: {last_error}")


ipc = IPCClient()


async def handle_ask(
    task_id: str,
    query: str,
    context: str,
    vault_dir: str,
    model: Optional[str] = None,
    env_keys: Optional[Dict[str, str]] = None,
):
    if env_keys:
        os.environ.update(env_keys)

    system_prompt = (
        "You are a helpful PKM assistant. You have access to the user's vault.\n"
        "You have tools to interact with the vault (search, read, write). Use them autonomously to fulfill the user's request.\n"
        "Answer the user's query based on the provided context from their notes and the results of your tool calls.\n"
        "Provide an informative and compact summary report.\n"
        "If the context does not contain the answer, say so, but still try to be helpful."
    )

    user_content = f"Context:\n{context}\n\nQuery: {query}" if context else query

    if os.environ.get("PKM_TEST_MOCK_LLM") == "1":
        await ipc.send_message(
            {
                "type": "result",
                "id": task_id,
                "status": "success",
                "data": {"response": f"Mocked response for: {user_content}"},
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
                models_to_try = ["gemini/gemini-3.1-flash-preview"]

        if not models_to_try:
            raise RuntimeError("No API keys found for any supported models.")

        resolved_model = models_to_try[0]

        tools = get_pkm_tools()

        skills_dirs = [
            os.path.expanduser("~/.agents/skills/pkm"),
        ]

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

        agent = Agent(
            session_id=f"pkm-ask-{task_id}",
            model=resolved_model,
            system_prompt=system_prompt,
            tools=tools,
            skills_dirs=skills_dirs,
            instruction_dirs=[vault_dir],
            max_iterations=1000,
            hooks={"on_tool_start": on_tool_start},
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


async def handle_zettelkasten_maintenance(
    task_id: str,
    vault_dir: str,
    model: Optional[str] = None,
    env_keys: Optional[Dict[str, str]] = None,
):
    if env_keys:
        os.environ.update(env_keys)

    system_prompt = (
        "You are an autonomous Zettelkasten maintainer.\n"
        "Your task is to execute the following streamlined workflow on the vault:\n"
        "1. Read recent daily logs/notes to distill insights.\n"
        "2. Identify opportunities to split large notes or merge similar ones.\n"
        "3. Use semantic search to discover and create new auto-linking opportunities between notes.\n"
        "4. Review and clean up stale or orphaned notes.\n"
        "Execute these steps autonomously using the tools provided. When you are finished, summarize your actions."
    )

    user_content = "Please perform the scheduled Zettelkasten maintenance workflow now."

    if os.environ.get("PKM_TEST_MOCK_LLM") == "1":
        await ipc.send_message(
            {
                "type": "result",
                "id": task_id,
                "status": "success",
                "data": {"response": f"Mocked maintenance response"},
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
                models_to_try = ["gemini/gemini-3.1-flash-preview"]

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

        agent = Agent(
            session_id=f"pkm-maint-{task_id}",
            model=resolved_model,
            system_prompt=system_prompt,
            tools=tools,
            skills_dirs=[],
            instruction_dirs=[vault_dir],
            max_iterations=1000,
            hooks={"on_tool_start": on_tool_start},
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


async def handle_task(msg: Dict[str, Any]):
    task_id = str(msg.get("id", ""))
    task_type = msg.get("task_type")

    env_vars = msg.get("env", {})
    for k, v in env_vars.items():
        os.environ[k] = v

    vault_dir = os.environ.get("PKM_VAULT_DIR", ".")

    if task_type == "ask":
        await handle_ask(
            task_id,
            msg.get("query", ""),
            msg.get("context", ""),
            vault_dir,
            msg.get("model"),
            msg.get("env_keys", {}),
        )
    elif task_type == "zettelkasten_maintenance":
        await handle_zettelkasten_maintenance(
            task_id,
            vault_dir,
            msg.get("model"),
            msg.get("env_keys", {}),
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
    await ipc.reader_loop()


if __name__ == "__main__":
    asyncio.run(main())
