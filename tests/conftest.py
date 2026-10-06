import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from hyperion import llm  # noqa: E402
from hyperion.agent import Hyperion  # noqa: E402
from hyperion.memory import SessionStore  # noqa: E402
from hyperion.rag import KnowledgeBase  # noqa: E402
from hyperion.workspace import Snapshot  # noqa: E402

HERO = pathlib.Path(__file__).resolve().parent.parent / "demo" / "hero"


class FakeIDE:
    """Stands in for ide-backend + the IDE frontend: serves files and executes SSE actions like the real IDE does."""

    def __init__(self, files: dict[str, str] | None = None):
        self.files = dict(files or {})
        self.log: list[dict] = []
        self.lag = 0  # number of snapshot() calls during which writes are still "in flight"
        self._pending: list[dict] = []
        self.error: str | None = None

    async def snapshot(self):
        if self.lag > 0:
            self.lag -= 1
        else:
            for a in self._pending:
                self._do(a)
            self._pending = []
        return Snapshot(dict(self.files), [], self.error)

    async def validate(self, path):
        return None

    def _do(self, a):
        act, p = a["action"], a.get("path", "")
        if act == "create_file":
            if p in self.files:
                return  # real IDE: "File already exists" error
            self.files[p] = a.get("content", "")
        elif act == "edit_file":
            self.files[p] = a.get("content", "")
        elif act == "delete_file":
            self.files.pop(p, None)
        elif act == "delete_folder":
            for k in [k for k in self.files if k.startswith(p + "/")]:
                del self.files[k]

    def receive(self, frame: str):
        if not frame.startswith("data: ") or frame.startswith("data: [DONE]"):
            return None
        obj = json.loads(frame[6:])
        if "action" in obj:
            self.log.append(obj)
            if self.lag:
                self._pending.append(obj)
            else:
                self._do(obj)
        return obj


def hero_files() -> dict[str, str]:
    return {str(p.relative_to(HERO)): p.read_text() for p in HERO.rglob("*") if p.is_file()}


class Chat:
    def __init__(self, agent: Hyperion, ide: FakeIDE, user="user-1"):
        self.agent, self.ide, self.user = agent, ide, user

    async def say(self, text: str, user: str | None = None) -> str:
        out = []
        self.actions = []
        async for frame in self.agent.chat(user or self.user, text):
            obj = self.ide.receive(frame)
            if obj is None:
                continue
            if "action" in obj:
                self.actions.append(obj)
            else:
                out.append(obj.get("response", ""))
        return "".join(out)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """By default the LLM is unreachable; tests opt in with the `fake_llm` fixture."""
    monkeypatch.setattr("hyperion.config.API_KEY", "")


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []
    state = {"reply": "FAKE LLM ANSWER"}

    async def stream(messages):
        calls.append(messages)
        r = state["reply"]
        for i in range(0, len(r), 20):
            yield r[i:i + 20]

    async def complete(messages):
        return "".join([t async for t in stream(messages)]).strip()

    monkeypatch.setattr(llm, "stream", stream)
    monkeypatch.setattr(llm, "complete", complete)
    return type("L", (), {"calls": calls, "state": state})


@pytest.fixture(scope="session")
def kb():
    return KnowledgeBase()


@pytest.fixture
def ide():
    return FakeIDE(hero_files())


@pytest.fixture
def chat(ide, kb):
    agent = Hyperion(workspace=ide, kb=kb, store=SessionStore(), verify_attempts=3, verify_delay=0)
    return Chat(agent, ide)
