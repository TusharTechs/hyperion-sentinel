import pytest

from hyperion.analyzer.common import load_yaml_docs
from hyperion.analyzer.engine import analyze_workspace
from hyperion.remediation import build_changes
from hyperion.workspace import Snapshot

from conftest import hero_files


async def fix_all(files):
    snap = Snapshot(dict(files))
    r = await analyze_workspace(snap)
    ch = build_changes(snap, [f for f in r.findings if f.automation_safety != "MANUAL_ONLY"])
    new = dict(files)
    for c in ch:
        new[c.path] = c.content
    return r, ch, new, await analyze_workspace(Snapshot(new))


async def test_hero_improves_and_resolves():
    r, ch, new, r2 = await fix_all(hero_files())
    assert r2.score > r.score and {c.path for c in ch} >= {"Dockerfile", "deployment.yaml", ".dockerignore", ".env.example"}
    rules_after = {f.rule for f in r2.findings}
    for gone in ("K8S-RESOURCES", "K8S-READINESS", "K8S-LIVENESS", "DF-LATEST", "DF-ROOT", "DF-DOCKERIGNORE", "CFG-NO-ENV-TEMPLATE", "DF-PIP-CACHE", "K8S-REPLICAS"):
        assert gone not in rules_after, gone
    assert "CFG-SECRET" in rules_after  # never auto-"fixed"


async def test_remediation_is_idempotent():
    _, _, new, r2 = await fix_all(hero_files())
    snap = Snapshot(new)
    again = build_changes(snap, [f for f in r2.findings if f.automation_safety != "MANUAL_ONLY"])
    assert again == [] or all(c.content == new.get(c.path) for c in again)


async def test_yaml_comments_and_valid_output():
    files = {"d.yaml": "# keep me\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: w  # inline note\nspec:\n  replicas: 1\n  template:\n    spec:\n      containers:\n        - name: w\n          image: nginx:1.27\n          ports:\n            - containerPort: 80\n"}
    _, ch, new, r2 = await fix_all(files)
    assert "# keep me" in new["d.yaml"] and "# inline note" in new["d.yaml"]
    docs, err = load_yaml_docs(new["d.yaml"])
    assert err is None and docs[0]["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "256Mi"


async def test_compose_fixes():
    files = {"docker-compose.yaml": "services:\n  a:\n    image: redis:latest\n    privileged: true\n"}
    _, ch, new, r2 = await fix_all(files)
    rules = {f.rule for f in r2.findings}
    assert not rules & {"CMP-LATEST", "CMP-RESTART", "CMP-RESOURCES", "CMP-PRIVILEGED"}
    assert "redis:7-alpine" in new["docker-compose.yaml"]


async def test_profile_fixes():
    files = {"p.yaml": "applicationProfile:\n  metadata: {name: x}\n  specs:\n    runtime:\n      containerImage: {uri: docker.io/library/nginx, tag: latest}\n    network:\n      ports:\n        - {port: 80, protocol: TCP, publicExposure: true}\n"}
    _, ch, new, r2 = await fix_all(files)
    assert "PROF-LATEST" not in {f.rule for f in r2.findings} and "PROF-PUBLIC" not in {f.rule for f in r2.findings}


async def test_unknown_image_is_never_auto_pinned():
    files = {"Dockerfile": "FROM myorg/private-thing:latest\n"}
    snap = Snapshot(files)
    r = await analyze_workspace(snap)
    f = next(x for x in r.findings if x.rule == "DF-LATEST")
    assert f.automation_safety == "MANUAL_ONLY"
    assert not any(c.path == "Dockerfile" and "private-thing" not in c.content for c in build_changes(snap, [f]))


async def test_dev_deps_moved():
    files = {"requirements.txt": "flask==2.0\npytest==8.0\nblack==24.0\n"}
    _, ch, new, _ = await fix_all(files)
    assert "pytest" not in new["requirements.txt"] and "pytest==8.0" in new["requirements-dev.txt"]


async def test_apt_multiline_run_edit():
    files = {"Dockerfile": "FROM debian:12-slim\nRUN apt-get update && \\\n    apt-get install -y curl\nUSER 1000\nHEALTHCHECK CMD true\n"}
    _, ch, new, _ = await fix_all(files)
    assert "--no-install-recommends" in new["Dockerfile"]
