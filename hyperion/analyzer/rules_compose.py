"""Docker Compose rules."""

from __future__ import annotations

import re

from ..models import CONFIRM_REQUIRED, MANUAL_ONLY, SAFE_AUTO
from .common import is_map, is_unpinned, line_of, mk, pin_suggestion, split_image
from .rules_docker import SECRET_NAME


def analyze_compose(path: str, doc):
    out = []
    services = doc.get("services")
    if not is_map(services):
        return out
    for sname, svc in services.items():
        if not is_map(svc):
            continue
        sl = line_of(services, sname)
        base = dict(target=f"service/{sname}", service=str(sname))
        img = svc.get("image")
        if isinstance(img, str):
            _, tag = split_image(img)
            if is_unpinned(tag):
                sug = pin_suggestion(img)
                out.append(mk("CMP-LATEST", "MEDIUM", "compose", path, f"Service `{sname}` image is not pinned",
                              f"line {line_of(svc, 'image')}: image: {img}",
                              "Unpinned tags change between pulls, so two edge sites can run different builds.",
                              "Pin a version" + (f", e.g. {sug}." if sug else "."),
                              SAFE_AUTO if sug else MANUAL_ONLY, line=line_of(svc, "image"), suggestion=sug, **base))
        elif "build" not in svc:
            continue
        if "restart" not in svc and "restart_policy" not in (svc.get("deploy") or {}):
            out.append(mk("CMP-RESTART", "MEDIUM", "compose", path, f"Service `{sname}` has no restart policy",
                          f"line {sl}: no restart / deploy.restart_policy",
                          "Edge nodes reboot and lose power; without a restart policy the service stays down.",
                          "Add `restart: unless-stopped`.", SAFE_AUTO, line=sl, **base))
        deploy_lim = ((svc.get("deploy") or {}).get("resources") or {}).get("limits") if is_map(svc.get("deploy")) else None
        if not deploy_lim and "mem_limit" not in svc and "cpus" not in svc:
            out.append(mk("CMP-RESOURCES", "HIGH", "compose", path, f"Service `{sname}` has no CPU/memory limits",
                          f"line {sl}: no deploy.resources.limits / mem_limit",
                          "An unbounded container can starve every other service on a small edge node.",
                          "Add deploy.resources.limits (suggested cpus 0.5, memory 256M).", SAFE_AUTO, line=sl, **base))
        if svc.get("privileged") is True:
            out.append(mk("CMP-PRIVILEGED", "CRITICAL", "compose", path, f"Service `{sname}` is privileged",
                          f"line {line_of(svc, 'privileged')}: privileged: true",
                          "Privileged containers have near-root access to the host.",
                          "Remove `privileged: true`.", CONFIRM_REQUIRED, line=line_of(svc, "privileged"), **base))
        if "healthcheck" not in svc:
            out.append(mk("CMP-HEALTHCHECK", "MEDIUM", "compose", path, f"Service `{sname}` has no healthcheck",
                          f"line {sl}: no healthcheck", "Compose cannot detect or restart a hung service without one.",
                          "Add a healthcheck for the service.", MANUAL_ONLY, line=sl, **base))
        env = svc.get("environment")
        pairs = []
        if is_map(env):
            pairs = [(k, v) for k, v in env.items()]
        elif isinstance(env, list):
            pairs = [tuple(str(e).split("=", 1)) if "=" in str(e) else (str(e), None) for e in env]
        for k, v in pairs:
            if SECRET_NAME.search(str(k)) and v not in (None, "") and not str(v).startswith("${"):
                out.append(mk("CFG-SECRET", "HIGH", "configuration", path, f"Service `{sname}` hardcodes a credential-like value",
                              f"line {sl}: environment {k}=<redacted>",
                              "Secrets committed to compose files leak through version control.",
                              "Use `${VAR}` interpolation with an untracked .env, or Docker secrets.", MANUAL_ONLY, line=sl))
        for vol in svc.get("volumes") or []:
            v = str(vol)
            if re.match(r"^(/|~|\.\.)", v.split(":")[0]) and not v.startswith("/var/run/docker.sock"):
                out.append(mk("CMP-HOSTMOUNT", "LOW", "compose", path, f"Service `{sname}` bind-mounts a host path",
                              f"line {sl}: volume {v.split(':')[0]}", "Host paths differ across edge nodes, hurting portability.",
                              "Prefer named volumes.", MANUAL_ONLY, line=sl))
                break
    for nname, net in (doc.get("networks") or {}).items() if is_map(doc.get("networks")) else []:
        if is_map(net) and net.get("external"):
            out.append(mk("CMP-EXTNET", "LOW", "compose", path, f"Network `{nname}` is external",
                          f"networks.{nname}.external: true", "The stack will not start unless that network pre-exists on every node.",
                          "Document or create the network as part of deployment.", MANUAL_ONLY))
    return out
