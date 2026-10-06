"""LLM access (OpenAI-compatible endpoint). Failures surface as LLMUnavailable, never as crashes."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from . import config


class LLMUnavailable(Exception):
    pass


_llm = None


def _get():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI

        _llm = ChatOpenAI(model=config.LLM_MODEL, base_url=config.LLM_BASE_URL, api_key=config.API_KEY or "missing",
                          max_completion_tokens=1500, temperature=0.2, timeout=config.LLM_TIMEOUT, max_retries=1)
    return _llm


def _check():
    if not config.API_KEY:
        raise LLMUnavailable("no API_KEY is configured for the language model")


def _to_messages(messages: list[dict]):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    m = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
    return [m[x["role"]](content=x["content"]) for x in messages]


async def stream(messages: list[dict]) -> AsyncIterator[str]:
    _check()
    try:
        async with asyncio.timeout(config.LLM_TIMEOUT + 15):
            async for chunk in _get().astream(_to_messages(messages)):
                if chunk.text:
                    yield chunk.text
    except LLMUnavailable:
        raise
    except Exception as exc:
        raise LLMUnavailable(f"{type(exc).__name__}: {str(exc)[:160]}") from exc


async def complete(messages: list[dict]) -> str:
    return "".join([t async for t in stream(messages)]).strip()
