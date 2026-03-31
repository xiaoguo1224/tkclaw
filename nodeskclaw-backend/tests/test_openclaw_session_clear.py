import json

import pytest

from app.services.openclaw_session import clear_main_session


class FakeFS:
    def __init__(self, files: dict[str, str] | None = None):
        self.files = files or {}

    async def read_text(self, path: str):
        return self.files.get(path)

    async def write_text(self, path: str, content: str) -> None:
        self.files[path] = content


@pytest.mark.asyncio
async def test_clear_main_session_resets_store_and_file():
    sessions_path = ".openclaw/agents/main/sessions/sessions.json"
    session_file = ".openclaw/agents/main/sessions/agent_main_main.jsonl"
    fs = FakeFS({
        sessions_path: json.dumps({
            "main": {
                "sessionId": "main",
                "sessionFile": "/root/.openclaw/agents/main/sessions/agent_main_main.jsonl",
                "model": "gpt-5",
            },
            "agent:main:desk-1": {
                "sessionId": "agent_main_desk-1",
                "sessionFile": "/root/.openclaw/agents/main/sessions/agent_main_desk-1.jsonl",
            },
        }),
        session_file: '{"type":"message"}\n',
    })

    await clear_main_session(fs)

    store = json.loads(fs.files[sessions_path])
    assert "main" not in store
    assert store["agent:main:main"]["sessionId"] == "agent_main_main"
    assert store["agent:main:main"]["sessionFile"] == "/root/.openclaw/agents/main/sessions/agent_main_main.jsonl"
    assert store["agent:main:main"]["model"] == "gpt-5"
    assert fs.files[session_file] == ""
