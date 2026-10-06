"""The primary demo story, end to end against a simulated IDE."""
import re


async def test_full_story(chat, ide):
    r = await chat.say("Prepare this application for edge deployment.")
    assert "EDGE READINESS REPORT" in r
    m = re.search(r"Edge Readiness: (\d+)/100", r)
    before = int(m.group(1))
    assert "HIGH" in r and "not an official HYPER-AI metric" in r
    assert "Sup3rS3cretPass" not in r  # secrets are never echoed

    r = await chat.say("What should I fix first?")
    assert "Why:" in r and "#" in r

    r = await chat.say("Fix everything you safely can.")
    assert "REMEDIATION PLAN" in r and "Safe changes" in r and "Nothing has been changed yet" in r
    assert chat.actions == []  # plan only: no state change before confirmation
    assert "python:latest" in ide.files["Dockerfile"]

    r = await chat.say("yes, all")
    assert {a["action"] for a in chat.actions} <= {"edit_file", "create_file"}
    assert "python:3.12-slim" in ide.files["Dockerfile"]
    assert "readinessProbe" in ide.files["deployment.yaml"]
    assert ".dockerignore" in ide.files and ".env.example" in ide.files
    assert "DB_PASSWORD=\n" in ide.files[".env.example"] and "Sup3rS3cretPass" not in ide.files[".env.example"]
    m = re.search(r"(\d+)/100 → (\d+)/100", r)
    assert int(m.group(1)) == before and int(m.group(2)) > before
    assert "improvement" in r and "Resolved" in r and "verified" in r

    r = await chat.say("What changed and why?")
    assert "Dockerfile" in r and "deployment.yaml" in r and "resolved" in r


async def test_second_issue_memory(chat, ide):
    await chat.say("Analyze my deployment")
    first_two = chat.agent.store.get("user-1").findings[:2]
    r = await chat.say("Fix the second issue")
    sess = chat.agent.store.get("user-1")
    assert sess.pending is not None
    target = first_two[1]
    if r.startswith("None of these"):
        assert target.automation_safety == "MANUAL_ONLY"
    else:
        assert "issue #2" in r
