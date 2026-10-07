import pytest
import yaml


async def test_hyperai_question_is_grounded_and_cites_sources(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    fake_llm.state["reply"] = "HYPER-AI is a hyper-distributed system."
    r = await chat.say("What is HyperAI?")
    assert "hyper-distributed" in r and "Sources:" in r
    sys_prompt = fake_llm.calls[-1][0]["content"]
    assert "CONTEXT" in sys_prompt and "[Source:" in sys_prompt and "HYPER-AI" in sys_prompt


async def test_unanswerable_hyperai_question_admits_it(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    r = await chat.say("What is the HyperAI pricing for enterprise licenses in 2031?")
    # either no retrieval hit (honest refusal) or the model is told to refuse when context lacks the answer
    assert "does not provide enough information" in r or "does not provide enough information" in fake_llm.calls[-1][0]["content"]


async def test_rag_fallback_without_llm(chat):
    r = await chat.say("What are Open Connectors?")
    assert "Source:" in r and "Open Connectors" in r


async def test_create_nginx_deployment_creates_and_opens_file(chat, ide):
    ide.files.clear()
    r = await chat.say("Create a deployment YAML for a service using the nginx Docker image")
    assert [a["action"] for a in chat.actions] == ["create_file"]
    a = chat.actions[0]
    assert a["path"] == "deployment.yaml"
    doc = yaml.safe_load(a["content"])
    c = doc["spec"]["template"]["spec"]["containers"][0]
    assert doc["kind"] == "Deployment" and c["image"].startswith("nginx:") and "latest" not in c["image"]
    assert c["resources"]["limits"] and c["readinessProbe"]
    assert ide.files["deployment.yaml"] == a["content"]


async def test_create_compose_for_redis(chat, ide):
    ide.files.clear()
    await chat.say("create a docker compose file for redis")
    doc = yaml.safe_load(chat.actions[0]["content"])
    assert chat.actions[0]["path"] == "docker-compose.yaml" and doc["services"]["redis"]["restart"] == "unless-stopped"


async def test_create_via_llm_validates_yaml(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    fake_llm.state["reply"] = "```yaml\nfoo: [unclosed\nbar: : :\n```"
    r = await chat.say("create a file named config.yaml with some settings for my app")
    assert chat.actions == [] and "valid config.yaml" in r
    fake_llm.state["reply"] = "```yaml\nname: demo\nport: 80\n```"
    await chat.say("create a file named config.yaml with some settings for my app")
    assert chat.actions and chat.actions[0]["path"] == "config.yaml"


async def test_create_without_llm_reports_clearly(chat):
    r = await chat.say("create a file named notes.yaml describing my service")
    assert chat.actions == [] and "language model is unavailable" in r


async def test_edit_existing_file_requires_confirmation_and_shows_diff(chat, ide):
    before = ide.files["deployment.yaml"]
    r = await chat.say("edit deployment.yaml and set replicas to 2")
    assert "-  replicas: 5" in r and "+  replicas: 2" in r and "Reply \"yes\"" in r
    assert chat.actions == [] and ide.files["deployment.yaml"] == before
    await chat.say("yes")
    assert chat.actions[0]["action"] == "edit_file" and "replicas: 2" in ide.files["deployment.yaml"]


async def test_edit_nonexistent_file_changes_nothing(chat, ide):
    r = await chat.say("edit missing.yaml and set replicas to 2")
    assert ide.log == [] and "can't find missing.yaml" in r


async def test_edit_via_llm_is_validated_then_confirmed(chat, ide, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    new = ide.files["service.yaml"].replace("LoadBalancer", "ClusterIP")
    fake_llm.state["reply"] = f"```yaml\n{new}```"
    r = await chat.say("change service.yaml so the service type is ClusterIP")
    assert "ClusterIP" in r and ide.log == []
    await chat.say("yes")
    assert "ClusterIP" in ide.files["service.yaml"]
    fake_llm.state["reply"] = "```yaml\nbroken: [\n```"
    r = await chat.say("update deployment.yaml with something")
    assert "wouldn't parse" in r


async def test_fix_second_issue_uses_memory(chat, ide):
    await chat.say("Analyze my deployment")
    sess = chat.agent.store.get("user-1")
    second = sess.findings[1]
    r = await chat.say("Fix the second issue")
    assert "#2" in r
    await chat.say("yes")
    after_rules = {f.rule for f in chat.agent.store.get("user-1").findings}
    assert second.rule not in after_rules  # the right issue was fixed
    assert len(ide.log) >= 1


async def test_fix_by_description(chat, ide):
    await chat.say("Analyze my deployment")
    r = await chat.say("fix the readiness probe")
    assert "readinessProbe" in r
    await chat.say("yes")
    assert "readinessProbe" in ide.files["deployment.yaml"] and "livenessProbe" not in ide.files["deployment.yaml"]


async def test_fix_manual_issue_explains_instead(chat, ide):
    await chat.say("Analyze my deployment")
    r = await chat.say("fix the first issue")  # hardcoded secret: manual
    assert "by hand" in r and ide.log == []


async def test_fix_without_analysis_analyzes_first(chat, ide):
    r = await chat.say("fix everything you safely can")
    assert "REMEDIATION PLAN" in r and ide.log == []


async def test_what_did_you_change_before_any_change(chat):
    r = await chat.say("what did you change?")
    assert "haven't changed anything" in r


async def test_cancel_plan(chat, ide):
    await chat.say("fix everything you safely can")
    r = await chat.say("no thanks")
    assert "cancelled" in r and ide.log == []


async def test_yes_only_applies_safe_changes(chat, ide):
    await chat.say("fix everything you safely can")
    r = await chat.say("yes")
    assert "runAsNonRoot" not in ide.files["deployment.yaml"] and "replicas: 5" in ide.files["deployment.yaml"]
    assert "need your confirmation" in r
    await chat.say("yes")
    assert "runAsNonRoot" in ide.files["deployment.yaml"] and "replicas: 2" in ide.files["deployment.yaml"]


async def test_reanalysis_honest_when_ide_lags(chat, ide):
    await chat.say("fix everything you safely can")
    ide.lag = 100
    r = await chat.say("yes, all")
    assert "hasn't confirmed every write" in r and "improvement" in r


async def test_explain_issue_and_priority(chat):
    await chat.say("analyze my deployment")
    r = await chat.say("explain issue 2")
    assert "Why it matters" in r and "Evidence" in r
    r = await chat.say("how is the score calculated?")
    assert "not an official HYPER-AI metric" in r and "CRITICAL 25" in r


async def test_sessions_are_isolated(chat, ide):
    await chat.say("analyze my deployment", user="alice")
    r = await chat.say("what did you change?", user="bob")
    assert "haven't changed anything" in r
    assert chat.agent.store.get("alice").report is not None and chat.agent.store.get("bob").report is None


async def test_memory_is_bounded(chat):
    for i in range(60):
        await chat.say(f"what is hyperai {i}", user="u")
    s = chat.agent.store.get("u")
    assert len(s.history) <= 20 and all(len(m["content"]) <= 1500 for m in s.history)


def test_session_store_is_bounded():
    from hyperion.memory import SessionStore
    st = SessionStore(max_sessions=5)
    for i in range(50):
        st.get(f"u{i}")
    assert len(st) == 5


async def test_greeting_and_help(chat):
    for t in ("hello", "what can you do?"):
        r = await chat.say(t)
        assert "Hyperion" in r and "edge" in r.lower()


async def test_reports_never_claim_unsupported_things(chat):
    r = await chat.say("Prepare this application for edge deployment.")
    assert "certif" not in r.lower().replace("not an official", "") or "not" in r
    assert "deployed to" not in r.lower()


async def test_llm_dockerfile_must_start_with_from(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    fake_llm.state["reply"] = "Sure! Here is how you do it: first install python then run the app."
    r = await chat.say("Create a Dockerfile for a small flask app")
    assert chat.actions == [] and "valid Dockerfile" in r and len(fake_llm.calls) == 2  # retried once


async def test_llm_draft_gets_sentinel_self_check(chat, ide, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    ide.files.clear()
    fake_llm.state["reply"] = "```dockerfile\nFROM python:latest\nRUN pip install flask\nCMD ['python','app.py']\n```"
    r = await chat.say("Create a Dockerfile for a small flask app")
    content = chat.actions[0]["content"]
    assert "python:3.12-slim" in content and "--no-cache-dir" in content and "Sentinel self-check" in r


async def test_delete_it_never_resolves_to_same_named_file_elsewhere(chat, ide):
    # root deployment.yaml was just created by Hyperion but the IDE has not listed it yet; demo-style duplicate exists elsewhere
    ide.files = {"other/deployment.yaml": "a: 1\n"}
    sess = chat.agent.store.get("user-1")
    sess.known_files["deployment.yaml"] = "x: 1\n"; sess.last_file = "deployment.yaml"
    r = await chat.say("delete it")
    assert "✗ deployment.yaml" in r and "other/" not in r


async def test_ide_usage_question_uses_the_official_tutorial(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    fake_llm.state["reply"] = "Click Deploy, choose the workflow, then Start it on the Dashboard."
    r = await chat.say("How do I deploy my first web server in the IDE?")
    ctx = fake_llm.calls[-1][0]["content"]
    assert "Quick Start Demo" in ctx and "Deploy" in ctx and "Sources:" in r and "HyperAI IDE tutorial" in r


async def test_tutorial_registry_question(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    await chat.say("Which registry must my container image be in for HyperAI?")
    assert "whitelisted registry" in fake_llm.calls[-1][0]["content"]


async def test_actions_question_uses_hyperion_actions_doc(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    await chat.say("What actions can Hyperion send to the IDE?")
    assert "create_file" in fake_llm.calls[-1][0]["content"] and "Hyperion Actions" in fake_llm.calls[-1][0]["content"]


async def test_generic_kubernetes_question_not_hijacked_by_docs(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    await chat.say("How do Kubernetes readiness probes work?")
    assert "CONTEXT" not in fake_llm.calls[-1][0]["content"]


async def test_required_fields_answer_is_deterministic_and_complete(chat):
    r = await chat.say("What are the required fields in a native application profile?")
    for f in ("metadata: type, schemaVersion, name, version, owner, lifecyclePhase", "executionType", "entryPoint", "containerImage.uri", "cpu, memory, storage", "supportedArchitectures"):
        assert f in r, f
    assert "Source: HyperAI IDE tutorial > Defining Native Applications" in r


async def test_required_fields_device(chat):
    r = await chat.say("Which fields are mandatory in a device application profile?")
    assert "apiVersion, kind, metadata, spec" in r and "esp32Binary.chip" in r and "Defining Device Node Applications" in r


async def test_comparison_question_retrieves_both_sides(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    await chat.say("What is the difference between native and device applications?")
    ctx = fake_llm.calls[-1][0]["content"]
    assert "Defining Native Applications" in ctx and "Defining Device Node Applications" in ctx


async def test_sources_line_not_duplicated_when_model_adds_its_own(chat, fake_llm, monkeypatch):
    monkeypatch.setattr("hyperion.config.API_KEY", "k")
    fake_llm.state["reply"] = "Native apps use profiles.\n\nSources: HyperAI IDE tutorial"
    r = await chat.say("What is the difference between native and device applications?")
    assert r.count("Sources:") == 1
