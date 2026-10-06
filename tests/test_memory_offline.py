"""Conversation memory, pronoun follow-ups, and operation with no IDE backend (how an evaluator may run the container)."""
import pytest

from hyperion.agent import Hyperion
from hyperion.memory import SessionStore

from conftest import Chat, FakeIDE


@pytest.fixture
def offline(kb):
    ide = FakeIDE({}); ide.error = "cannot reach the IDE backend at http://x (refused)"
    return Chat(Hyperion(workspace=ide, kb=kb, store=SessionStore(), verify_attempts=1, verify_delay=0), ide)


async def test_remembers_name(chat):
    r = await chat.say("My name is Bob")
    assert "Bob" in r and chat.actions == []
    r = await chat.say("What's my name?")
    assert r == "Your name is Bob."


async def test_name_not_known(chat):
    assert "haven't told me your name" in await chat.say("what is my name?")


async def test_names_are_per_user(chat):
    await chat.say("my name is Alice", user="a")
    assert "haven't told" in await chat.say("what's my name", user="b")


async def test_remembers_service_name(chat):
    await chat.say("My service is called payments-api")
    assert "payments-api" in await chat.say("what is my service called?")


async def test_recall_last_question(chat):
    await chat.say("What is HyperAI?")
    await chat.say("What are Open Connectors?")
    r = await chat.say("what was my last question?")
    assert "Open Connectors" in r
    assert "HyperAI" in await chat.say("what was my first question?")


async def test_recap(chat):
    await chat.say("What is HyperAI?")
    assert "HyperAI" in await chat.say("recap our conversation")


async def test_offline_create_then_delete_it(offline):
    r = await offline.say("Create a deployment YAML for a service using the nginx Docker image")
    assert [a["action"] for a in offline.actions] == ["create_file"]
    path = offline.actions[0]["path"]
    assert path in offline.agent.store.get("user-1").known_files
    assert path in await offline.say("what file did you just create?")
    r = await offline.say("now delete it")
    assert offline.actions == [] and path in r and "Reply \"yes\"" in r  # confirmation first, even offline
    await offline.say("yes")
    assert [(a["action"], a["path"]) for a in offline.actions] == [("delete_file", path)]
    assert path not in offline.agent.store.get("user-1").known_files


async def test_offline_delete_unknown_file_still_asks(offline):
    r = await offline.say("delete old.yaml")
    assert "permanently delete" in r and "can't reach the IDE workspace" in r and offline.actions == []
    await offline.say("no")
    assert offline.ide.log == []


async def test_offline_edit_it_requires_confirmation(offline):
    await offline.say("Create a deployment YAML for a service using the nginx Docker image")
    r = await offline.say("set replicas to 3 in it")
    assert "replicas: 3" in r and "Reply \"yes\"" in r and offline.actions == []
    await offline.say("yes")
    assert offline.actions[0]["action"] == "edit_file" and "replicas: 3" in offline.actions[0]["content"]


async def test_create_for_it_uses_remembered_image(chat, ide):
    ide.files.clear()
    await chat.say("I want to run redis at the edge")
    r = await chat.say("create a docker compose file for it")
    assert "redis" in chat.actions[0]["content"]


async def test_followup_pronoun_after_online_create(chat, ide):
    ide.files.clear()
    await chat.say("Create a deployment YAML for a service using the nginx Docker image")
    await chat.say("delete it")
    await chat.say("yes")
    assert "deployment.yaml" not in ide.files


async def test_unrelated_chitchat_still_refused(chat):
    r = await chat.say("what's the best pizza topping")
    assert "focused on helping" in r
