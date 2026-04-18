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


class IPCClient:
    def __init__(self):
        self.request_counter = 0

    def send_message(self, msg: Dict[str, Any]):
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()

    def read_message(self) -> Optional[Dict[str, Any]]:
        line = sys.stdin.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON: {e}")
            return None

    def call_llm(
        self, messages: List[Dict[str, str]], model: Optional[str] = None
    ) -> str:
        self.request_counter += 1
        req_id = f"llm_req_{self.request_counter}"

        req = {"type": "llm_request", "id": req_id, "messages": messages}
        if model:
            req["model"] = model

        self.send_message(req)

        while True:
            msg = self.read_message()
            if not msg:
                raise RuntimeError("EOF while waiting for LLM response")

            if msg.get("type") == "llm_response" and msg.get("id") == req_id:
                return msg.get("content", "")
            elif msg.get("type") == "llm_error" and msg.get("id") == req_id:
                raise RuntimeError(f"LLM Error: {msg.get('message')}")
            else:
                logger.warning(
                    f"Unexpected message while waiting for LLM response: {msg}"
                )


ipc = IPCClient()


def handle_ask(task_id: str, query: str, vault_dir: str):
    messages = [
        {
            "role": "system",
            "content": "You are a helpful PKM assistant. You have access to the user's vault.",
        },
        {"role": "user", "content": query},
    ]

    try:
        response = ipc.call_llm(messages)
        ipc.send_message(
            {
                "type": "result",
                "id": task_id,
                "status": "success",
                "data": {"response": response},
            }
        )
    except Exception as e:
        ipc.send_message({"type": "error", "id": task_id, "message": str(e)})


def handle_zettelkasten_maintenance(task_id: str, file_path: str, vault_dir: str):
    try:
        full_path = os.path.join(vault_dir, file_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        messages = [
            {
                "role": "system",
                "content": "You are a Zettelkasten maintainer. Extract tags and suggest wikilinks for the following note. Output JSON with 'tags' (list of strings) and 'links' (list of strings).",
            },
            {"role": "user", "content": content},
        ]

        response = ipc.call_llm(messages)

        try:
            if response.startswith("```json"):
                response = response[7:-3].strip()
            elif response.startswith("```"):
                response = response[3:-3].strip()

            result_data = json.loads(response)
        except json.JSONDecodeError:
            result_data = {"tags": [], "links": [], "raw_response": response}

        ipc.send_message(
            {"type": "result", "id": task_id, "status": "success", "data": result_data}
        )
    except Exception as e:
        ipc.send_message({"type": "error", "id": task_id, "message": str(e)})


def main():
    logger.info("PKM LLM Worker started")

    vault_dir = os.environ.get("PKM_VAULT_DIR", ".")

    while True:
        try:
            msg = ipc.read_message()
            if not msg:
                break

            msg_type = msg.get("type")
            if msg_type == "task":
                task_id = str(msg.get("id", ""))
                task_type = msg.get("task_type")

                if task_type == "ask":
                    handle_ask(task_id, msg.get("query", ""), vault_dir)
                elif task_type == "zettelkasten_maintenance":
                    handle_zettelkasten_maintenance(
                        task_id, msg.get("file_path", ""), vault_dir
                    )
                else:
                    ipc.send_message(
                        {
                            "type": "error",
                            "id": task_id,
                            "message": f"Unknown task type: {task_type}",
                        }
                    )
            else:
                logger.warning(f"Unexpected message type: {msg_type}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")


if __name__ == "__main__":
    main()
