"""HYPER-AI application-profile rules (native `applicationProfile` / device `hyper.ai/v1` formats)."""

from __future__ import annotations

import re

from ..models import CONFIRM_REQUIRED, MANUAL_ONLY, SAFE_AUTO
from .common import is_map, is_unpinned, line_of, mk, pin_suggestion, split_image


def detect_profile(doc) -> str | None:
    if not is_map(doc):
        return None
    if "applicationProfile" in doc:
        return "native"
    if str(doc.get("apiVersion", "")).startswith("hyper.ai/") or (doc.get("kind") == "Application" and "spec" in doc):
        return "device"
    meta = doc.get("metadata")
    if is_map(meta) and meta.get("type") in ("native", "device", "integration") and ("specs" in doc or "spec" in doc):
        return "native"  # legacy layout used by the IDE's bundled sample templates
    return None


def _cpu_milli(v) -> float | None:
    m = re.match(r"^(\d+(?:\.\d+)?)(m)?$", str(v).strip())
    if not m:
        return None
    return float(m.group(1)) * (1 if m.group(2) else 1000)


def _mem_gi(v) -> float | None:
    m = re.match(r"^(\d+(?:\.\d+)?)(Mi|Gi|Ti)$", str(v).strip())
    if not m:
        return None
    return float(m.group(1)) * {"Mi": 1 / 1024, "Gi": 1, "Ti": 1024}[m.group(2)]


def _dig(node, *keys):
    for k in keys:
        if not is_map(node):
            return None
        node = node.get(k)
    return node


DOCKER_HUB_HOSTS = {"docker.io", "index.docker.io", "registry-1.docker.io", "registry.hub.docker.com"}


def registry_host(ref: str) -> str | None:
    """Registry host of an image reference, or None for Docker Hub short names (`nginx`, `user/app`)."""
    first = str(ref).split("/", 1)[0] if "/" in str(ref) else ""
    if first and ("." in first or ":" in first or first == "localhost"):
        return first.lower()
    return None


def registry_finding(path, name, ref, line, target):
    host = registry_host(ref)
    if host is None or host in DOCKER_HUB_HOSTS:
        return None
    return mk("PROF-REGISTRY", "LOW", "hyperai-profile", path, f"Profile `{name}` image comes from `{host}`, which may not be a whitelisted registry",
              f"line {line}: image {ref}",
              "The HyperAI tutorial requires the container to be in a public registry whitelisted by HyperAI (for example Docker Hub); an image elsewhere may fail to deploy.",
              "Publish the image to a public whitelisted registry such as Docker Hub (or confirm with the platform team that this one is whitelisted).",
              MANUAL_ONLY, line=line, target=target)


def analyze_profile(path: str, doc, kind: str):
    out = []
    root = doc.get("applicationProfile") if kind == "native" and "applicationProfile" in doc else doc
    if not is_map(root):
        return out
    name = _dig(root, "metadata", "name") or _dig(root, "spec", "app", "name") or path

    if kind == "native":
        specs = root.get("specs") if is_map(root.get("specs")) else {}
        runtime = specs.get("runtime") if is_map(specs.get("runtime")) else {}
        ci = runtime.get("containerImage") if is_map(runtime.get("containerImage")) else (
            specs.get("image") if is_map(specs.get("image")) else None)
        if ci:
            uri, tag = str(ci.get("uri", "")), ci.get("tag")
            tag = str(tag) if tag is not None else None
            if uri and is_unpinned(tag):
                sug = pin_suggestion(uri)
                out.append(mk("PROF-LATEST", "MEDIUM", "hyperai-profile", path, f"Profile `{name}` container image tag is not pinned",
                              f"line {line_of(ci, 'tag') or line_of(ci)}: {uri}:{tag or '(none)'}",
                              "An unpinned tag lets the image change under a profile that is deployed to many edge nodes.",
                              "Set containerImage.tag to a specific version" + (f" (e.g. {sug.rsplit(':', 1)[1]})." if sug else "."),
                              SAFE_AUTO if sug and "tag" in ci else MANUAL_ONLY, line=line_of(ci, "tag") or line_of(ci),
                              target=f"{name}:image", tag=sug.rsplit(":", 1)[1] if sug else None))
        if ci and str(ci.get("uri", "")):
            rf = registry_finding(path, name, str(ci.get("uri")), line_of(ci, "uri") or line_of(ci), f"{name}:registry")
            if rf:
                out.append(rf)
        res = specs.get("resources") if is_map(specs.get("resources")) else (
            root.get("resources") if is_map(root.get("resources")) else {})
        cpu, mem = _cpu_milli(res.get("cpu")), _mem_gi(res.get("memory"))
        if (cpu and cpu > 4000) or (mem and mem > 8):
            out.append(mk("PROF-HEAVY", "LOW", "hyperai-profile", path, f"Profile `{name}` requests large resources",
                          f"cpu={res.get('cpu')}, memory={res.get('memory')} (thresholds 4000m / 8Gi)",
                          "Requests above typical edge-node capacity limit where the scheduler can place this app.",
                          "Right-size cpu/memory to measured usage.", MANUAL_ONLY, line=line_of(res, "cpu"), target=f"{name}:res"))
        net = specs.get("network") if is_map(specs.get("network")) else root.get("network")
        for p in (net or {}).get("ports") or [] if is_map(net) else []:
            if is_map(p) and p.get("publicExposure") is True:
                out.append(mk("PROF-PUBLIC", "MEDIUM", "hyperai-profile", path, f"Profile `{name}` exposes port {p.get('port')} publicly",
                              f"line {line_of(p, 'publicExposure')}: publicExposure: true",
                              "Public exposure of an edge service widens its attack surface.",
                              "Set publicExposure: false unless external access is required.", CONFIRM_REQUIRED,
                              line=line_of(p, "publicExposure"), target=f"{name}:port{p.get('port')}", port=p.get("port")))
        cons = specs.get("constraints") if is_map(specs.get("constraints")) else root.get("constraints")
        archs = (cons or {}).get("supportedArchitectures") if is_map(cons) else None
        if isinstance(archs, list) and archs and not any("arm" in str(a).lower() for a in archs):
            out.append(mk("PROF-ARCH", "LOW", "hyperai-profile", path, f"Profile `{name}` does not declare arm64 support",
                          f"supportedArchitectures: {list(map(str, archs))}",
                          "Many edge devices are ARM-based; without arm64 the scheduler will not place this app on them.",
                          "If the image supports arm64, add it to supportedArchitectures.", MANUAL_ONLY, line=line_of(cons, "supportedArchitectures"),
                          target=f"{name}:arch"))
        if is_map(cons) and not cons.get("securityLevel") and not cons.get("dataClassification"):
            out.append(mk("PROF-SECURITY", "LOW", "hyperai-profile", path, f"Profile `{name}` declares no securityLevel/dataClassification",
                          "constraints has neither field", "Placement decisions cannot take data sensitivity into account.",
                          "Declare securityLevel and dataClassification.", MANUAL_ONLY, target=f"{name}:sec"))
    else:  # device
        spec = root.get("spec") if is_map(root.get("spec")) else {}
        wl = spec.get("workload") if is_map(spec.get("workload")) else {}
        di = wl.get("dockerImage") if is_map(wl.get("dockerImage")) else None
        if di and isinstance(di.get("image"), str):
            _, tag = split_image(di["image"])
            if is_unpinned(tag):
                sug = pin_suggestion(di["image"])
                out.append(mk("PROF-LATEST", "MEDIUM", "hyperai-profile", path, f"Device profile `{name}` image is not pinned",
                              f"line {line_of(di, 'image')}: {di['image']}",
                              "An unpinned tag lets the image change under a profile deployed to many devices.",
                              "Pin a specific version.", MANUAL_ONLY, line=line_of(di, "image"), target=f"{name}:image"))
        if di and isinstance(di.get("image"), str):
            rf = registry_finding(path, name, di["image"], line_of(di, "image"), f"{name}:registry")
            if rf:
                out.append(rf)
        for blk, urlk in (("androidApk", "apkUrl"), ("esp32Binary", "binaryUrl")):
            b = wl.get(blk)
            if is_map(b):
                url = str(b.get(urlk, ""))
                if url.startswith("http://"):
                    out.append(mk("PROF-INSECURE-URL", "MEDIUM", "hyperai-profile", path, f"Device profile `{name}` downloads over plain HTTP",
                                  f"line {line_of(b, urlk)}: {urlk} uses http://",
                                  "A plain-HTTP download can be tampered with in transit and then flashed/installed on a device.",
                                  "Use https:// and set sha256.", MANUAL_ONLY, line=line_of(b, urlk), target=f"{name}:{blk}:url"))
                if not b.get("sha256"):
                    out.append(mk("PROF-NO-CHECKSUM", "MEDIUM", "hyperai-profile", path, f"Device profile `{name}` has no sha256 for its {blk} artifact",
                                  f"{blk}.sha256 missing", "Without a checksum the device cannot verify what it installs.",
                                  "Add the artifact's sha256.", MANUAL_ONLY, line=line_of(b), target=f"{name}:{blk}:sha"))
    return out


def validation_findings(path: str, report: dict | None):
    """Turn the IDE validator's report into one aggregated finding."""
    if not report:
        return []
    errs, warns = report.get("errors") or [], report.get("warnings") or []
    out = []
    if errs:
        ex = "; ".join(f"line {e.get('line')}: {e.get('message')}" for e in errs[:3])
        out.append(mk("PROF-INVALID", "HIGH", "hyperai-profile", path,
                      f"HYPER-AI IDE validation reports {len(errs)} error(s)",
                      ex + ("…" if len(errs) > 3 else ""),
                      "A profile that fails validation cannot be reliably registered or scheduled.",
                      "Fix the reported fields (the IDE highlights them in the editor).", MANUAL_ONLY, line=errs[0].get("line")))
    if warns:
        ex = "; ".join(f"line {w.get('line')}: {w.get('message')}" for w in warns[:3])
        out.append(mk("PROF-WARN", "LOW", "hyperai-profile", path, f"HYPER-AI IDE validation reports {len(warns)} warning(s)",
                      ex + ("…" if len(warns) > 3 else ""), "Unknown or deprecated fields may be ignored by the platform.",
                      "Review the warnings in the editor.", MANUAL_ONLY, line=warns[0].get("line")))
    return out
