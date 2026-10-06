"""Deterministic remediation: turn findings into concrete file changes.

Only findings with a registered fixer are fixable; nothing here depends on the LLM.
Every YAML result is re-parsed before it is offered, so a bad edit is dropped, not emitted.
"""

from __future__ import annotations

import io
import posixpath
import re
from dataclasses import dataclass, field

from .analyzer.common import is_map, load_yaml_docs, yaml_loader
from .analyzer.engine import DOCKERIGNORE_TEXT
from .analyzer.rules_k8s import DEFAULT_RESOURCES
from .models import CONFIRM_REQUIRED, SAFE_AUTO, Finding
from .workspace import Snapshot


@dataclass
class Change:
    path: str
    action: str  # "create" | "edit"
    content: str
    before: str | None
    findings: list[Finding] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- text (Dockerfile / requirements)

def _span(lines: list[str], n: int) -> tuple[int, int]:
    """0-based [start, end] physical lines of the logical instruction starting at 1-based line n."""
    i = n - 1
    j = i
    while j < len(lines) - 1 and lines[j].rstrip().endswith("\\"):
        j += 1
    return i, j


def _sub_in_span(lines, n, pattern, repl) -> bool:
    i, j = _span(lines, n)
    for k in range(i, j + 1):
        new, c = re.subn(pattern, repl, lines[k], count=1)
        if c:
            lines[k] = new
            return True
    return False


def _fix_dockerfile(content: str, items: list[Finding]) -> tuple[str, list[tuple[Finding, str]]]:
    lines = content.split("\n")
    done: list[tuple[Finding, str]] = []
    add_user = add_hc = None
    for f in sorted(items, key=lambda x: -(x.line or 0)):
        if f.rule in ("DF-LATEST", "DF-FULL-BASE") and f.fix.get("suggestion"):
            old, new = f.fix["target"], f.fix["suggestion"]
            if _sub_in_span(lines, f.line, re.escape(old), new):
                done.append((f, f"Dockerfile line {f.line}: `FROM {old}` → `FROM {new}`"))
        elif f.rule == "DF-APT-RECOMMENDS":
            if _sub_in_span(lines, f.line, r"\b(apt(?:-get)?\s+install)\b", r"\1 --no-install-recommends"):
                done.append((f, f"Dockerfile line {f.line}: added `--no-install-recommends`"))
        elif f.rule == "DF-PIP-CACHE":
            if _sub_in_span(lines, f.line, r"\b(pip3?\s+install)\b", r"\1 --no-cache-dir"):
                done.append((f, f"Dockerfile line {f.line}: added `--no-cache-dir` to pip install"))
        elif f.rule == "DF-ROOT":
            add_user = f
        elif f.rule == "DF-HEALTHCHECK":
            add_hc = f
    def insert_before_cmd(new_lines):
        last_from = max((i for i, l in enumerate(lines) if l.strip().upper().startswith("FROM ")), default=0)
        idx = next((i for i in range(len(lines) - 1, last_from, -1)
                    if lines[i].strip().upper().startswith(("CMD", "ENTRYPOINT"))), None)
        if idx is None:
            while lines and lines[-1] == "":
                lines.pop()
            lines.extend(new_lines + [""])
        else:
            lines[idx:idx] = new_lines + [""]

    if add_hc is not None and add_hc.fix.get("port"):
        port = add_hc.fix["port"]
        insert_before_cmd([f"HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c \"import socket; socket.create_connection(('127.0.0.1', {port}), 2)\""])
        done.append((add_hc, f"Dockerfile: added a TCP HEALTHCHECK on port {port}"))
    if add_user is not None:
        # insert before the last CMD/ENTRYPOINT of the final stage, else append
        last_from = max((i for i, l in enumerate(lines) if l.strip().upper().startswith("FROM ")), default=0)
        idx = next((i for i in range(len(lines) - 1, last_from, -1)
                    if lines[i].strip().upper().startswith(("CMD", "ENTRYPOINT"))), None)
        if idx is None:
            while lines and lines[-1] == "":
                lines.pop()
            lines += ["USER 10001:10001", ""]
        else:
            lines[idx:idx] = ["USER 10001:10001", ""]
        done.append((add_user, "Dockerfile: added `USER 10001:10001` before the start command"))
    return "\n".join(lines), done


def _fix_requirements(content: str, items: list[Finding]):
    done, remove, moved = [], set(), []
    for f in items:
        if f.rule == "DEP-DEV-IN-PROD":
            remove |= set(f.fix.get("remove_lines", []))
            done.append((f, f"requirements: moved {len(f.fix.get('remove_lines', []))} dev package(s) to requirements-dev.txt"))
    lines = content.split("\n")
    kept = [l for i, l in enumerate(lines, 1) if i not in remove]
    moved = [l for i, l in enumerate(lines, 1) if i in remove]
    return "\n".join(kept), done, moved


# ---------------------------------------------------------------- YAML

def _dump_docs(docs: list, original: str) -> str:
    y = yaml_loader()
    buf = io.StringIO()
    y.dump_all(docs, buf) if len(docs) > 1 else y.dump(docs[0], buf)
    out = buf.getvalue()
    if original.startswith("---") and not out.startswith("---"):
        out = "---\n" + out
    return out


def _container(doc, f: Finding):
    from .analyzer.rules_k8s import pod_spec_of
    pod, _ = pod_spec_of(doc)
    return pod[f.fix["container_key"]][f.fix["container"]], pod


def _fix_yaml(content: str, items: list[Finding]):
    docs, err = load_yaml_docs(content)
    if err or not docs:
        return content, []
    # analyzer indexes docs after dropping empty ones, same as load_yaml_docs
    done: list[tuple[Finding, str]] = []
    for f in items:
        try:
            msg = _apply_yaml_fix(docs, f)
        except Exception:
            msg = None
        if msg:
            done.append((f, msg))
    if not done:
        return content, []
    new = _dump_docs(docs, content)
    _, err2 = load_yaml_docs(new)
    if err2:
        return content, []
    return new, done


def _apply_yaml_fix(docs, f: Finding) -> str | None:
    from ruamel.yaml.comments import CommentedMap
    r = f.rule
    p = f.file
    if r.startswith("K8S-") or r.startswith("PROF-") or r.startswith("CMP-"):
        pass
    if r == "K8S-RESOURCES":
        c, _ = _container(docs[f.fix["doc_index"]], f)
        res = c.get("resources")
        if not is_map(res):
            res = CommentedMap(); c["resources"] = res
        for section in ("requests", "limits"):
            sec = res.get(section)
            if not is_map(sec):
                sec = CommentedMap(); res[section] = sec
            for k in ("cpu", "memory"):
                if k not in sec:
                    sec[k] = DEFAULT_RESOURCES[section][k]
        rq, lm = DEFAULT_RESOURCES["requests"], DEFAULT_RESOURCES["limits"]
        return f"{f.fix['target']}: set resources requests {rq['cpu']}/{rq['memory']}, limits {lm['cpu']}/{lm['memory']}"
    if r in ("K8S-READINESS", "K8S-LIVENESS"):
        c, _ = _container(docs[f.fix["doc_index"]], f)
        port = f.fix.get("port")
        if not port:
            return None
        probe = CommentedMap(); ts = CommentedMap(); ts["port"] = port; probe["tcpSocket"] = ts
        probe["initialDelaySeconds"] = 5 if r == "K8S-READINESS" else 15
        probe["periodSeconds"] = 10
        c[f.fix["probe"]] = probe
        return f"{f.fix['target']}: added {f.fix['probe']} (tcpSocket :{port})"
    if r == "K8S-LATEST" and f.fix.get("suggestion"):
        c, _ = _container(docs[f.fix["doc_index"]], f)
        old = c["image"]; c["image"] = f.fix["suggestion"]
        return f"{f.fix['target']}: image `{old}` → `{f.fix['suggestion']}`"
    if r == "K8S-NONROOT":
        c, _ = _container(docs[f.fix["doc_index"]], f)
        sc = c.get("securityContext")
        if not is_map(sc):
            sc = CommentedMap(); c["securityContext"] = sc
        sc["runAsNonRoot"] = True; sc["runAsUser"] = 10001
        return f"{f.fix['target']}: set securityContext runAsNonRoot=true, runAsUser=10001"
    if r == "K8S-PRIVILEGED":
        c, _ = _container(docs[f.fix["doc_index"]], f)
        c["securityContext"]["privileged"] = False
        return f"{f.fix['target']}: privileged → false"
    if r in ("K8S-HOSTNET", "K8S-HOSTPID", "K8S-HOSTIPC"):
        from .analyzer.rules_k8s import pod_spec_of
        pod, _ = pod_spec_of(docs[f.fix["doc_index"]])
        del pod[f.fix["flag"]]
        return f"{f.fix['target'].split(':')[0]}: removed {f.fix['flag']}"
    if r == "K8S-REPLICAS":
        d = docs[f.fix["doc_index"]]
        old = d["spec"]["replicas"]; d["spec"]["replicas"] = f.fix["replicas"]
        return f"{f.fix['target']}: replicas {old} → {f.fix['replicas']}"
    if r == "K8S-SVC-TYPE":
        d = docs[f.fix["doc_index"]]
        old = d["spec"]["type"]; d["spec"]["type"] = "ClusterIP"
        return f"{f.fix['target']}: service type {old} → ClusterIP"
    # compose
    if r.startswith("CMP-"):
        doc = docs[0]
        svc = doc["services"][f.fix["service"]]
        if r == "CMP-LATEST" and f.fix.get("suggestion"):
            old = svc["image"]; svc["image"] = f.fix["suggestion"]
            return f"service {f.fix['service']}: image `{old}` → `{f.fix['suggestion']}`"
        if r == "CMP-RESTART":
            svc["restart"] = "unless-stopped"
            return f"service {f.fix['service']}: added restart: unless-stopped"
        if r == "CMP-RESOURCES":
            d = svc.get("deploy")
            if not is_map(d):
                d = CommentedMap(); svc["deploy"] = d
            res = d.get("resources")
            if not is_map(res):
                res = CommentedMap(); d["resources"] = res
            lim = CommentedMap(); lim["cpus"] = "0.5"; lim["memory"] = "256M"; res["limits"] = lim
            return f"service {f.fix['service']}: added deploy.resources.limits (0.5 CPU / 256M)"
        if r == "CMP-PRIVILEGED":
            del svc["privileged"]
            return f"service {f.fix['service']}: removed privileged: true"
    # HYPER-AI profile
    if r == "PROF-LATEST" and f.fix.get("tag"):
        d = docs[0]
        root = d.get("applicationProfile", d)
        specs = root["specs"]
        ci = specs.get("runtime", {}).get("containerImage") if is_map(specs.get("runtime")) else None
        ci = ci if is_map(ci) else specs["image"]
        old = ci.get("tag"); ci["tag"] = f.fix["tag"]
        return f"profile {f.fix['target'].split(':')[0]}: image tag `{old}` → `{f.fix['tag']}`"
    if r == "PROF-PUBLIC":
        d = docs[0]
        root = d.get("applicationProfile", d)
        specs = root["specs"] if "specs" in root else root
        for pt in specs["network"]["ports"]:
            if pt.get("port") == f.fix["port"]:
                pt["publicExposure"] = False
        return f"profile {f.fix['target'].split(':')[0]}: port {f.fix['port']} publicExposure → false"
    return None


# ---------------------------------------------------------------- entry points

def fixable(f: Finding) -> bool:
    return f.automation_safety in (SAFE_AUTO, CONFIRM_REQUIRED) and f.rule in FIXABLE_RULES


FIXABLE_RULES = {
    "DF-LATEST", "DF-FULL-BASE", "DF-ROOT", "DF-HEALTHCHECK", "DF-APT-RECOMMENDS", "DF-PIP-CACHE", "DF-DOCKERIGNORE",
    "CFG-NO-ENV-TEMPLATE", "K8S-RESOURCES", "K8S-READINESS", "K8S-LIVENESS", "K8S-LATEST", "K8S-NONROOT",
    "K8S-PRIVILEGED", "K8S-HOSTNET", "K8S-HOSTPID", "K8S-HOSTIPC", "K8S-REPLICAS", "K8S-SVC-TYPE",
    "CMP-LATEST", "CMP-RESTART", "CMP-RESOURCES", "CMP-PRIVILEGED", "PROF-LATEST", "PROF-PUBLIC", "DEP-DEV-IN-PROD",
}


def build_changes(snap: Snapshot, findings: list[Finding]) -> list[Change]:
    """Produce file changes that resolve the given findings (all must already be approved)."""
    by_file: dict[str, list[Finding]] = {}
    changes: list[Change] = []
    for f in findings:
        if not fixable(f):
            continue
        if f.rule == "DF-DOCKERIGNORE":
            tgt = posixpath.join(f.fix.get("folder", ""), ".dockerignore")
            if tgt not in snap.files:
                changes.append(Change(tgt, "create", DOCKERIGNORE_TEXT, None, [f], [f"created {tgt} (excludes .git, .env, caches, node_modules…)"]))
        elif f.rule == "CFG-NO-ENV-TEMPLATE":
            tgt = posixpath.join(f.fix.get("folder", ""), ".env.example")
            if tgt not in snap.files:
                body = "# Generated by Hyperion Sentinel - variable names only; copy to .env and fill in\n" + \
                       "\n".join(f"{k}=" for k in f.fix.get("keys", [])) + "\n"
                changes.append(Change(tgt, "create", body, None, [f], [f"created {tgt} with {len(f.fix.get('keys', []))} variable name(s) (no values)"]))
        else:
            by_file.setdefault(f.file, []).append(f)
    for path, items in sorted(by_file.items()):
        original = snap.files.get(path)
        if original is None:
            continue
        from .analyzer.common import kind_of_file
        kind = kind_of_file(path)
        if kind == "dockerfile":
            new, done = _fix_dockerfile(original, items)
        elif kind == "requirements":
            new, done, moved = _fix_requirements(original, items)
            if moved and done:
                dev_path = posixpath.join(posixpath.dirname(path), "requirements-dev.txt")
                if dev_path not in snap.files:
                    changes.append(Change(dev_path, "create", "\n".join(moved) + "\n", None, [], [f"created {dev_path} with {len(moved)} dev package(s)"]))
        elif kind in ("yaml", "compose"):
            new, done = _fix_yaml(original, items)
        else:
            continue
        if done and new != original:
            changes.append(Change(path, "edit", new, original, [f for f, _ in done], [m for _, m in done]))
    return changes
