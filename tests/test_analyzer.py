"""Each finding type exercised on its own, plus score and secret-handling properties."""
import pytest

from hyperion.analyzer.engine import analyze_workspace
from hyperion.models import Finding, compute_score
from hyperion.workspace import Snapshot

DEPLOY = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: web
          image: nginx:1.27
          ports:
            - containerPort: 80
{extra}"""

GOOD_C = """          resources:
            requests: {cpu: 100m, memory: 64Mi}
            limits: {cpu: 200m, memory: 128Mi}
          readinessProbe: {tcpSocket: {port: 80}}
          livenessProbe: {tcpSocket: {port: 80}}
          securityContext: {runAsNonRoot: true, runAsUser: 1000}
"""


async def rules(files: dict[str, str]):
    r = await analyze_workspace(Snapshot(files))
    return {f.rule for f in r.findings}, r


@pytest.mark.parametrize("name,files,rule", [
    ("latest tag", {"Dockerfile": "FROM python:latest\nUSER 1000\nHEALTHCHECK CMD true\n"}, "DF-LATEST"),
    ("untagged", {"Dockerfile": "FROM python\nUSER 1000\n"}, "DF-LATEST"),
    ("full base", {"Dockerfile": "FROM python:3.12\nUSER 1000\n"}, "DF-FULL-BASE"),
    ("root", {"Dockerfile": "FROM python:3.12-slim\nCMD ['x']\n"}, "DF-ROOT"),
    ("explicit root", {"Dockerfile": "FROM python:3.12-slim\nUSER root\n"}, "DF-ROOT"),
    ("healthcheck", {"Dockerfile": "FROM alpine:3.20\nUSER 1000\n"}, "DF-HEALTHCHECK"),
    ("apt recommends", {"Dockerfile": "FROM debian:12-slim\nRUN apt-get install -y curl\n"}, "DF-APT-RECOMMENDS"),
    ("apt clean", {"Dockerfile": "FROM debian:12-slim\nRUN apt-get install -y --no-install-recommends curl\n"}, "DF-APT-CLEAN"),
    ("pip cache", {"Dockerfile": "FROM python:3.12-slim\nRUN pip install flask\n"}, "DF-PIP-CACHE"),
    ("build tools", {"Dockerfile": "FROM python:3.12-slim\nRUN apt-get install -y gcc\n"}, "DF-BUILD-TOOLS"),
    ("dockerignore", {"Dockerfile": "FROM alpine:3.20\n"}, "DF-DOCKERIGNORE"),
    ("env secret", {"Dockerfile": "FROM alpine:3.20\nENV DB_PASSWORD=hunter2hunter2\n"}, "CFG-SECRET"),
    ("no from", {"Dockerfile": "RUN echo hi\n"}, "DF-NO-FROM"),
    ("k8s resources", {"d.yaml": DEPLOY.format(extra="")}, "K8S-RESOURCES"),
    ("k8s readiness", {"d.yaml": DEPLOY.format(extra="")}, "K8S-READINESS"),
    ("k8s liveness", {"d.yaml": DEPLOY.format(extra="")}, "K8S-LIVENESS"),
    ("k8s nonroot", {"d.yaml": DEPLOY.format(extra="")}, "K8S-NONROOT"),
    ("k8s latest", {"d.yaml": DEPLOY.replace("nginx:1.27", "nginx:latest").format(extra="")}, "K8S-LATEST"),
    ("k8s replicas", {"d.yaml": DEPLOY.replace("replicas: 1", "replicas: 9").format(extra="")}, "K8S-REPLICAS"),
    ("k8s placement", {"d.yaml": DEPLOY.format(extra="")}, "K8S-PLACEMENT"),
    ("k8s privileged", {"d.yaml": DEPLOY.format(extra="          securityContext:\n            privileged: true\n")}, "K8S-PRIVILEGED"),
    ("k8s hostnet", {"d.yaml": DEPLOY.replace("    spec:\n      containers", "    spec:\n      hostNetwork: true\n      containers").format(extra="")}, "K8S-HOSTNET"),
    ("k8s hostpid", {"d.yaml": DEPLOY.replace("    spec:\n      containers", "    spec:\n      hostPID: true\n      containers").format(extra="")}, "K8S-HOSTPID"),
    ("k8s hostipc", {"d.yaml": DEPLOY.replace("    spec:\n      containers", "    spec:\n      hostIPC: true\n      containers").format(extra="")}, "K8S-HOSTIPC"),
    ("k8s svc", {"s.yaml": "apiVersion: v1\nkind: Service\nmetadata: {name: s}\nspec:\n  type: NodePort\n  ports: [{port: 80}]\n"}, "K8S-SVC-TYPE"),
    ("compose latest", {"docker-compose.yaml": "services:\n  a:\n    image: redis:latest\n"}, "CMP-LATEST"),
    ("compose restart", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\n"}, "CMP-RESTART"),
    ("compose resources", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\n"}, "CMP-RESOURCES"),
    ("compose privileged", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\n    privileged: true\n"}, "CMP-PRIVILEGED"),
    ("compose healthcheck", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\n"}, "CMP-HEALTHCHECK"),
    ("compose hostmount", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\n    volumes: ['/data:/data']\n"}, "CMP-HOSTMOUNT"),
    ("compose extnet", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\nnetworks:\n  n:\n    external: true\n"}, "CMP-EXTNET"),
    ("compose secret", {"docker-compose.yaml": "services:\n  a:\n    image: redis:7\n    environment:\n      API_TOKEN: abcd1234efgh\n"}, "CFG-SECRET"),
    ("unpinned deps", {"requirements.txt": "flask\nrequests==2.0\n"}, "DEP-UNPINNED"),
    ("loose deps", {"requirements.txt": "flask>=2\n"}, "DEP-LOOSE"),
    ("dev deps", {"requirements.txt": "flask==2.0\npytest==8.0\n"}, "DEP-DEV-IN-PROD"),
    ("heavy deps", {"requirements.txt": "torch==2.0\n"}, "DEP-HEAVY"),
    ("native deps", {"requirements.txt": "psycopg2==2.9\n"}, "DEP-NATIVE"),
    ("many deps", {"requirements.txt": "\n".join(f"pkg{i}==1.0" for i in range(45))}, "DEP-MANY"),
    ("npm unpinned", {"package.json": '{"dependencies": {"left-pad": "*"}}'}, "DEP-UNPINNED"),
    ("npm dev", {"package.json": '{"dependencies": {"jest": "^29"}}'}, "DEP-DEV-IN-PROD"),
    ("bad json", {"package.json": "{not json"}, "CFG-MALFORMED"),
    ("env secret file", {".env": "API_KEY=abcd1234efgh5678\n"}, "CFG-SECRET"),
    ("aws key", {"config.py": 'KEY = "AKIAABCDEFGHIJKLMNOP"\n'}, "CFG-SECRET"),
    ("private key", {"k.txt": "-----BEGIN RSA PRIVATE KEY-----\nabc\n"}, "CFG-SECRET"),
    ("external url", {"app.py": 'URL = "https://api.vendor-cloud.io/v1"\n'}, "CFG-EXTERNAL-URL"),
    ("env template", {".env": "A=1\nB=2\n"}, "CFG-NO-ENV-TEMPLATE"),
    ("malformed yaml", {"bad.yaml": "a: [1, 2\nb: : :\n"}, "CFG-MALFORMED"),
    ("no dockerfile", {"app.py": "print(1)\n", "requirements.txt": "flask==1.0\n"}, "PRJ-NO-DOCKERFILE"),
    ("no deploy manifest", {"Dockerfile": "FROM alpine:3.20\n"}, "PRJ-NO-DEPLOY"),
    ("no readme", {"app.py": "print(1)\n"}, "PRJ-NO-README"),
    ("no dep manifest", {"app.py": "print(1)\n"}, "PRJ-NO-DEPS"),
    ("profile latest", {"p.yaml": "applicationProfile:\n  metadata: {name: x, type: native}\n  specs:\n    runtime:\n      containerImage: {uri: docker.io/library/nginx, tag: latest}\n"}, "PROF-LATEST"),
    ("profile public", {"p.yaml": "applicationProfile:\n  metadata: {name: x}\n  specs:\n    network:\n      ports:\n        - {port: 80, protocol: TCP, publicExposure: true}\n"}, "PROF-PUBLIC"),
    ("profile arch", {"p.yaml": "applicationProfile:\n  metadata: {name: x}\n  specs:\n    constraints:\n      supportedArchitectures: [x86_64]\n"}, "PROF-ARCH"),
    ("profile heavy", {"p.yaml": "applicationProfile:\n  metadata: {name: x}\n  specs:\n    resources: {cpu: 16000m, memory: 64Gi, storage: 1Ti}\n"}, "PROF-HEAVY"),
    ("device http", {"p.yaml": "apiVersion: hyper.ai/v1\nkind: Application\nmetadata: {name: d}\nspec:\n  workload:\n    kind: AndroidApk\n    androidApk: {apkUrl: 'http://x.io/a.apk', packageName: a.b}\n"}, "PROF-INSECURE-URL"),
    ("device checksum", {"p.yaml": "apiVersion: hyper.ai/v1\nkind: Application\nmetadata: {name: d}\nspec:\n  workload:\n    kind: AndroidApk\n    androidApk: {apkUrl: 'https://x.io/a.apk', packageName: a.b}\n"}, "PROF-NO-CHECKSUM"),
])
async def test_finding_detected(name, files, rule):
    found, r = await rules(files)
    assert rule in found, (name, found)
    f = next(x for x in r.findings if x.rule == rule)
    assert f.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW") and f.evidence and f.why_it_matters and f.recommended_fix
    assert f.automation_safety in ("SAFE_AUTO", "CONFIRM_REQUIRED", "MANUAL_ONLY")


async def test_clean_k8s_has_no_workload_findings():
    doc = DEPLOY.replace("{extra}", GOOD_C).replace("      containers", "      nodeSelector: {k: v}\n      containers")
    found, r = await rules({"d.yaml": doc})
    assert not {x for x in found if x.startswith("K8S-")}, found
    assert any("resource requests and limits" in g.finding for g in r.good)


async def test_clean_dockerfile():
    found, r = await rules({"Dockerfile": "FROM python:3.12-slim\nRUN pip install --no-cache-dir flask\nEXPOSE 80\nHEALTHCHECK CMD true\nUSER 1000\nCMD ['x']\n", ".dockerignore": ".git\n"})
    assert not {x for x in found if x.startswith("DF-")}, found


async def test_multistage_internal_stage_not_flagged_as_unpinned():
    found, _ = await rules({"Dockerfile": "FROM golang:1.22-alpine AS build\nRUN go build\nFROM build AS final\nUSER 1000\nHEALTHCHECK CMD true\nFROM scratch\n", ".dockerignore": "x"})
    assert "DF-LATEST" not in found


async def test_secrets_are_never_printed():
    secret = "Zx9!verySecretValue42"
    files = {".env": f"DB_PASSWORD={secret}\n", "app.py": 'T = "AKIAABCDEFGHIJKLMNOP"\n', "d/Dockerfile": f"FROM alpine:3.20\nENV TOKEN={secret}\n"}
    r = await analyze_workspace(Snapshot(files))
    blob = " ".join(str(f.to_dict()) for f in r.findings)
    assert secret not in blob and "AKIAABCDEFGHIJKLMNOP" not in blob
    from hyperion import render
    assert secret not in render.report_text(r, r.findings, full=True)


async def test_placeholder_and_example_files_not_flagged():
    found, _ = await rules({".env.example": "DB_PASSWORD=changeme\n", "x.py": "API_KEY = os.environ['API_KEY']\n", ".env": "PASSWORD=<your-password>\n"})
    assert "CFG-SECRET" not in found


async def test_empty_workspace():
    r = await analyze_workspace(Snapshot({}))
    assert r.findings == [] and r.files_inspected == []


async def test_multi_document_yaml_and_findings_have_lines():
    doc = DEPLOY.format(extra="") + "---\n" + DEPLOY.replace("name: web", "name: second").format(extra="")
    found, r = await rules({"two.yaml": doc})
    lines = {f.line for f in r.findings if f.rule == "K8S-RESOURCES"}
    assert len(lines) == 2 and None not in lines


def test_score_is_deterministic_and_bounded():
    def f(sev, rule):
        return Finding(rule=rule, severity=sev, category="x", file="a", finding="", evidence="", why_it_matters="", recommended_fix="")
    assert compute_score([]) == 100
    assert compute_score([f("HIGH", "a")]) == 85
    assert compute_score([f("HIGH", "a"), f("MEDIUM", "b"), f("LOW", "c")]) == 100 - 15 - 7 - 3
    many = [f("LOW", "same") for _ in range(100)]
    assert 100 - compute_score(many) <= 9  # repeats + tier cap
    assert compute_score([f("CRITICAL", str(i)) for i in range(20)] + [f("HIGH", str(i + 50)) for i in range(20)]) >= 0
    assert compute_score(many) == compute_score(list(reversed(many)))


async def test_analyzer_survives_binary_and_odd_files():
    files = {"x.yaml": "\x00\x01\x02", "Dockerfile": "FROM", "docker-compose.yml": "services: 5", "p.yaml": "applicationProfile: 3",
             "d.yaml": "kind: Deployment\napiVersion: apps/v1\nspec: 1\n", "requirements.txt": "-r other.txt\n===\n"}
    r = await analyze_workspace(Snapshot(files))
    assert isinstance(r.score, int)
