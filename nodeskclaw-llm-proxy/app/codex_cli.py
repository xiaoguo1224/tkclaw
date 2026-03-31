import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings

# SYNC: 以下三个常量与 nodeskclaw-backend/app/services/codex_provider.py 保持同步
CODEX_PROVIDER = "codex"
CODEX_CLI_SENTINEL = "__CODEX_CLI__"
CODEX_MODELS = [
    {"id": "gpt-5.4", "name": "gpt-5.4"},
    {"id": "gpt-5.3-codex", "name": "gpt-5.3-codex"},
    {"id": "gpt-5.3-codex-spark", "name": "gpt-5.3-codex-spark"},
    {"id": "gpt-5", "name": "gpt-5"},
    {"id": "o3", "name": "o3"},
    {"id": "o4-mini", "name": "o4-mini"},
    {"id": "gpt-5-mini", "name": "gpt-5-mini"},
    {"id": "gpt-5-nano", "name": "gpt-5-nano"},
    {"id": "o3-mini", "name": "o3-mini"},
    {"id": "codex-mini-latest", "name": "Codex Mini"},
]


@dataclass
class CodexExecutionResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class CodexExecutionError(Exception):
    pass


def list_codex_models() -> list[dict[str, Any]]:
    return list(CODEX_MODELS)


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _build_prompt(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user").strip() or "user"
        content = _extract_text_content(message.get("content"))
        if not content:
            continue
        parts.append(f"{role.upper()}:\n{content}")
    return "\n\n".join(parts).strip()


def _normalize_model(model: str | None) -> str:
    raw = (model or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        prefix, suffix = raw.split("/", 1)
        if prefix == CODEX_PROVIDER and suffix.strip():
            return suffix.strip()
    return raw


def _parse_codex_jsonl(stdout: str) -> tuple[str, int, int, int, str | None]:
    messages: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0
    error_message: str | None = None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = str(event.get("type") or "")
        if event_type == "error":
            message = str(event.get("message") or "").strip()
            if message:
                error_message = message
            continue

        if event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and str(item.get("type") or "") == "agent_message":
                text = str(item.get("text") or "").strip()
                if text:
                    messages.append(text)
            elif isinstance(item, dict) and str(item.get("type") or "") == "error":
                message = str(item.get("message") or "").strip()
                if message:
                    error_message = message
            continue

        if event_type == "turn.completed":
            usage = event.get("usage")
            if isinstance(usage, dict):
                prompt_tokens = int(usage.get("input_tokens") or prompt_tokens or 0)
                completion_tokens = int(usage.get("output_tokens") or completion_tokens or 0)
                cached_tokens = int(usage.get("cached_input_tokens") or cached_tokens or 0)
            continue

        if event_type == "turn.failed":
            err = event.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or "").strip()
                if message:
                    error_message = message

    return "\n\n".join(messages).strip(), prompt_tokens, completion_tokens, cached_tokens, error_message


async def run_codex_chat_completion(
    *,
    messages: list[dict[str, Any]],
    model: str | None,
    api_key: str | None = None,
) -> CodexExecutionResult:
    prompt = _build_prompt(messages)
    if not prompt:
        raise CodexExecutionError("Codex 请求缺少可执行的消息内容")

    command = settings.CODEX_COMMAND.strip() or "codex"
    normalized_model = _normalize_model(model)
    args = [command, "exec", "--json"]
    if settings.CODEX_SKIP_GIT_REPO_CHECK:
        args.append("--skip-git-repo-check")
    if settings.CODEX_BYPASS_APPROVALS_AND_SANDBOX:
        args.append("--dangerously-bypass-approvals-and-sandbox")
    if normalized_model:
        args.extend(["--model", normalized_model])
    args.append("-")

    env = os.environ.copy()
    if settings.CODEX_HOME:
        env["CODEX_HOME"] = settings.CODEX_HOME
    if api_key and api_key.strip() and api_key.strip() != CODEX_CLI_SENTINEL:
        env["OPENAI_API_KEY"] = api_key.strip()

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError as exc:
        raise CodexExecutionError("llm-proxy 未安装 codex CLI，请先安装并重启服务") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode("utf-8")),
            timeout=settings.CODEX_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise CodexExecutionError("Codex 执行超时，请稍后重试") from exc

    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")
    text, prompt_tokens, completion_tokens, cached_tokens, parsed_error = _parse_codex_jsonl(stdout_text)

    if process.returncode != 0:
        detail = parsed_error or _first_non_empty_line(stderr_text) or _first_non_empty_line(stdout_text)
        if detail:
            raise CodexExecutionError(detail)
        raise CodexExecutionError(f"Codex 执行失败，退出码 {process.returncode}")

    if not text:
        raise CodexExecutionError("Codex 未返回可用内容")

    return CodexExecutionResult(
        text=text,
        model=normalized_model or "codex",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
    )


def build_chat_completion_response(
    *,
    result: CodexExecutionResult,
    request_model: str | None,
) -> dict[str, Any]:
    created = int(time.time())
    model = request_model or result.model
    return {
        "id": f"chatcmpl-codex-{created}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
        },
    }


def build_chat_completion_stream_events(
    *,
    result: CodexExecutionResult,
    request_model: str | None,
) -> list[dict[str, Any]]:
    created = int(time.time())
    response_id = f"chatcmpl-codex-{created}"
    model = request_model or result.model
    return [
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": result.text}, "finish_reason": None}],
        },
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
            },
        },
    ]
