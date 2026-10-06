import pytest

from hyperion.workspace import PathError, safe_path

from conftest import FakeIDE


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "a/../../b", "/etc/passwd", "..", "../", "a/../..", "C:\\Windows\\x", "~/x", "a\x00b", "a/b\\..\\c",
    "", "   ", ".git/config", "x/.ssh/id_rsa", "a" * 300, "a/%2e%2e/b", "foo|bar", "x" * 150 + "/y",
])
def test_unsafe_paths_rejected(bad):
    with pytest.raises(PathError):
        safe_path(bad)


@pytest.mark.parametrize("ok,norm", [("demo/app.yaml", "demo/app.yaml"), ("./a.yaml", "a.yaml"), ("a//b.yaml", "a/b.yaml"),
                                     (".env", ".env"), (".dockerignore", ".dockerignore"), ("Dockerfile", "Dockerfile"), ("'x.yaml'", "x.yaml")])
def test_safe_paths_normalised(ok, norm):
    assert safe_path(ok) == norm


async def test_delete_requires_confirmation(chat, ide):
    r = await chat.say("delete demo.txt")  # nonexistent
    assert "isn't in the workspace" in r and ide.log == []
    r = await chat.say("delete Dockerfile")
    assert "permanently delete" in r and chat.actions == [] and "Dockerfile" in ide.files
    r = await chat.say("no")
    assert "cancelled" in r and "Dockerfile" in ide.files and ide.log == []
    await chat.say("delete Dockerfile")
    await chat.say("yes")
    assert [a["action"] for a in ide.log] == ["delete_file"] and "Dockerfile" not in ide.files


async def test_unrelated_yes_does_not_delete(chat, ide):
    r = await chat.say("yes")
    assert ide.log == []


async def test_confirmation_does_not_carry_over_after_cancel(chat, ide):
    await chat.say("delete Dockerfile")
    await chat.say("no")
    await chat.say("yes")
    assert "Dockerfile" in ide.files and ide.log == []


@pytest.mark.parametrize("text", ["delete everything", "delete all files", "remove the whole workspace", "delete *"])
async def test_mass_deletion_refused(chat, ide, text):
    r = await chat.say(text)
    assert "won't delete files in bulk" in r and ide.log == [] and len(ide.files) > 3


async def test_delete_traversal_refused(chat, ide):
    for t in ("delete ../../etc/passwd.txt", "remove /etc/hosts.conf"):
        r = await chat.say(t)
        assert ide.log == [] and ("not allowed" in r or "isn't in the workspace" in r or "can't delete" in r)


async def test_delete_more_than_three_refused(chat, ide):
    r = await chat.say("delete a.txt b.txt c.txt d.txt")
    assert ide.log == [] and "more than 3" in r


async def test_ambiguous_name_not_deleted():
    from hyperion.agent import Hyperion
    from hyperion.memory import SessionStore
    from conftest import Chat
    ide = FakeIDE({"a/app.yaml": "x: 1\n", "b/app.yaml": "x: 2\n"})
    ch = Chat(Hyperion(workspace=ide, store=SessionStore()), ide)
    r = await ch.say("delete app.yaml")
    assert "several files" in r and ide.log == []


async def test_folder_delete_confirms_and_counts(chat, ide):
    ide.files["old/a.yaml"] = "a: 1\n"; ide.files["old/b.yaml"] = "b: 1\n"
    r = await chat.say("delete the folder old")
    assert "2 file(s) inside" in r and ide.log == []
    await chat.say("yes")
    assert ide.log[0]["action"] == "delete_folder" and not any(k.startswith("old/") for k in ide.files)


async def test_create_with_traversal_path_refused(chat, ide):
    r = await chat.say("create file ../../evil.yaml with some config")
    assert ide.log == []
    r = await chat.say("create a deployment yaml named /etc/cron.d/x.yaml using the nginx image")
    assert ide.log == []


async def test_create_over_existing_file_requires_confirmation(chat, ide):
    before = ide.files["deployment.yaml"]
    r = await chat.say("Create deployment.yaml for a service using the nginx Docker image")
    assert "already exists" in r and ide.files["deployment.yaml"] == before and ide.log == []
    await chat.say("no")
    assert ide.files["deployment.yaml"] == before
    await chat.say("Create deployment.yaml for a service using the nginx Docker image")
    await chat.say("yes")
    assert ide.files["deployment.yaml"] != before and ide.log[-1]["action"] == "edit_file"


async def test_empty_workspace(kb):
    from hyperion.agent import Hyperion
    from hyperion.memory import SessionStore
    from conftest import Chat
    ide = FakeIDE({})
    r = await Chat(Hyperion(workspace=ide, kb=kb, store=SessionStore()), ide).say("Analyze my deployment")
    assert "workspace is empty" in r


async def test_backend_unreachable(kb):
    from hyperion.agent import Hyperion
    from hyperion.memory import SessionStore
    from conftest import Chat
    ide = FakeIDE({"a.yaml": "x: 1\n"}); ide.error = "cannot reach the IDE backend at http://x (boom)"
    ch = Chat(Hyperion(workspace=ide, kb=kb, store=SessionStore()), ide)
    r = await ch.say("Prepare this application for edge deployment.")
    assert "couldn't read the workspace" in r and ide.log == []
    r = await ch.say("delete a.yaml")
    assert ide.log == []


async def test_large_file_skipped_by_ide_reader():
    import httpx
    from hyperion import config
    from hyperion.workspace import IDEWorkspace

    big = "x" * (config.MAX_FILE_BYTES + 10)

    def handler(req: httpx.Request):
        if req.url.path.endswith("/files"):
            return httpx.Response(200, json=[{"name": "big.yaml", "type": "file", "path": "big.yaml"}, {"name": "ok.yaml", "type": "file", "path": "ok.yaml"}])
        return httpx.Response(200, json={"content": big if req.url.params["path"] == "big.yaml" else "a: 1\n"})

    ws = IDEWorkspace("http://ide/api", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    snap = await ws.snapshot()
    assert "ok.yaml" in snap.files and "big.yaml" not in snap.files and any("big.yaml" in s for s in snap.skipped)


async def test_ide_unreachable_reports_error():
    from hyperion.workspace import IDEWorkspace
    snap = await IDEWorkspace("http://127.0.0.1:9/api").snapshot()
    assert snap.error and not snap.files


async def test_malformed_yaml_in_workspace_gives_finding_not_crash(chat, ide):
    ide.files["broken.yaml"] = "a: [1, 2\nb: : :\n"
    r = await chat.say("Analyze my deployment")
    assert "YAML cannot be parsed" in r
