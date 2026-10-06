import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import main
from hyperion.agent import Hyperion
from hyperion.memory import SessionStore


@pytest.fixture
def client(ide, kb, monkeypatch):
    monkeypatch.setattr(main, "agent", Hyperion(workspace=ide, kb=kb, store=SessionStore(), verify_attempts=1, verify_delay=0))
    return TestClient(main.app)


def frames(resp):
    out = []
    for block in resp.text.split("\n\n"):
        if block.strip():
            assert block.startswith("data: "), block
            out.append(block[6:])
    return out


def test_valid_request_streams_sse(client):
    r = client.post("/chat", json={"user_id": "u-1", "text": "hello"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    fr = frames(r)
    assert fr[-1] == "[DONE]"
    body = [json.loads(f) for f in fr[:-1]]
    assert all("response" in b or "action" in b for b in body)
    assert "Hyperion" in "".join(b.get("response", "") for b in body)


def test_cors_enabled(client):
    r = client.options("/chat", headers={"Origin": "http://localhost:5050", "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": "content-type"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5050")


@pytest.mark.parametrize("payload", [{}, {"text": "hi"}, {"user_id": "u"}, {"user_id": "", "text": "x"}, {"user_id": 5, "text": None},
                                     [], "string"])
def test_malformed_payloads_rejected(client, payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_non_json_body_rejected(client):
    assert client.post("/chat", content="not json", headers={"Content-Type": "application/json"}).status_code == 422


def test_blank_text_gets_friendly_reply(client):
    r = client.post("/chat", json={"user_id": "u", "text": "   "})
    assert r.status_code == 200 and "Tell me what" in r.text and frames(r)[-1] == "[DONE]"


def test_huge_text_is_truncated_not_fatal(client):
    r = client.post("/chat", json={"user_id": "u", "text": "weather " * 50000})
    assert r.status_code == 200 and frames(r)[-1] == "[DONE]"


def test_agent_exception_keeps_stream_well_formed(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("kaboom")
        yield  # pragma: no cover
    monkeypatch.setattr(main.agent, "chat", boom)
    r = client.post("/chat", json={"user_id": "u", "text": "hi"})
    assert r.status_code == 200 and "went wrong" in r.text and frames(r)[-1] == "[DONE]"


def test_timeout_is_reported(client, monkeypatch):
    async def slow(*a, **k):
        await asyncio.sleep(5)
        yield "data: {}\n\n"
    monkeypatch.setattr(main.agent, "chat", slow)
    monkeypatch.setattr(main, "REQUEST_TIMEOUT", 0.2)
    r = client.post("/chat", json={"user_id": "u", "text": "hi"})
    assert "too long" in r.text and frames(r)[-1] == "[DONE]"


def test_llm_failure_degrades_gracefully(client, monkeypatch, kb):
    """No API key / LLM down: HYPER-AI questions fall back to documentation excerpts instead of erroring."""
    r = client.post("/chat", json={"user_id": "u", "text": "What is the Application Profile Manager?"})
    txt = r.text
    assert "language model is unavailable" in txt and "Source:" in txt and frames(r)[-1] == "[DONE]"


def test_llm_error_mid_request(client, monkeypatch):
    from hyperion import llm

    async def failing(messages):
        raise llm.LLMUnavailable("connection refused")
        yield  # pragma: no cover
    monkeypatch.setattr(llm, "stream", failing)
    r = client.post("/chat", json={"user_id": "u", "text": "How do Kubernetes readiness probes work?"})
    assert "can't reach the language model" in r.text and frames(r)[-1] == "[DONE]"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
