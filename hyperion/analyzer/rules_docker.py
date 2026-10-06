"""Dockerfile rules."""

from __future__ import annotations

import re

from ..models import CONFIRM_REQUIRED, MANUAL_ONLY, SAFE_AUTO
from .common import FULL_VARIANTS, image_base, mk, pin_suggestion, split_image

SECRET_NAME = re.compile(r"(pass(word)?|secret|token|api[_-]?key|private[_-]?key|access[_-]?key)", re.I)


def logical_lines(content: str):
    """Yield (first_line_no, text) joining backslash continuations; comments dropped."""
    buf, start = "", None
    for i, raw in enumerate(content.splitlines(), 1):
        s = raw.rstrip()
        if start is None:
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            start = i
        elif s.lstrip().startswith("#"):
            continue
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        yield start, buf.strip()
        buf, start = "", None
    if start is not None and buf.strip():
        yield start, buf.strip()


def analyze_dockerfile(path: str, content: str):
    out = []
    instr = [(n, t) for n, t in logical_lines(content)]
    froms = [(n, t) for n, t in instr if t.upper().startswith("FROM ")]
    if not froms:
        out.append(mk("DF-NO-FROM", "HIGH", "dockerfile", path, "Dockerfile has no FROM instruction",
                      "No FROM line found", "An image cannot be built without a base image.",
                      "Add a FROM <image>:<tag> line.", MANUAL_ONLY))
        return out

    stage_names, bases = set(), []
    for n, t in froms:
        m = re.match(r"FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", t, re.I)
        if not m:
            continue
        ref, alias = m.group(1), m.group(2)
        if alias:
            stage_names.add(alias.lower())
        if ref.lower() == "scratch" or ref.lower() in stage_names and not alias:
            bases.append((n, ref, True))
            continue
        bases.append((n, ref, ref.lower() in stage_names))

    for n, ref, internal in bases:
        if internal or ref.startswith("$") or "${" in ref:
            continue
        name, tag = split_image(ref)
        base = image_base(name)
        unpinned = tag is None or tag.lower() == "latest"
        if unpinned:
            sug = pin_suggestion(ref)
            out.append(mk("DF-LATEST", "MEDIUM", "dockerfile", path,
                          "Base image is not pinned (uses `latest` or no tag)",
                          f"line {n}: FROM {ref}",
                          "Unpinned images change between builds, making edge rollouts unreproducible and hard to roll back.",
                          f"Pin an explicit version" + (f", e.g. {sug}." if sug else " (choose a version your app is tested with)."),
                          SAFE_AUTO if sug else MANUAL_ONLY, line=n, target=ref, suggestion=sug))
        elif base in FULL_VARIANTS and not re.search(r"slim|alpine|distroless|minimal|busybox", tag or ""):
            out.append(mk("DF-FULL-BASE", "LOW", "dockerfile", path,
                          f"Base image `{base}:{tag}` is a full-size variant",
                          f"line {n}: FROM {ref}",
                          "Full distro images are much larger than -slim/-alpine variants, which costs bandwidth and storage on constrained edge nodes.",
                          f"Consider {name}:{tag}-slim after verifying compatibility.",
                          CONFIRM_REQUIRED, line=n, target=ref, suggestion=f"{name}:{tag}-slim"))

    last_stage_start = froms[-1][0]
    last = [(n, t) for n, t in instr if n >= last_stage_start]

    # root user
    user_lines = [(n, t) for n, t in last if t.upper().startswith("USER ")]
    if not user_lines or user_lines[-1][1].split(None, 1)[1].strip().split(":")[0] in ("root", "0"):
        ev = f"line {user_lines[-1][0]}: {user_lines[-1][1]}" if user_lines else "No USER instruction in the final stage"
        out.append(mk("DF-ROOT", "MEDIUM", "dockerfile", path, "Container runs as root",
                      ev, "A root process in a compromised container has far more power over the host and the other workloads on a shared edge node.",
                      "Add a non-root USER (e.g. USER 10001:10001) after installing dependencies.",
                      CONFIRM_REQUIRED, line=user_lines[-1][0] if user_lines else froms[-1][0]))

    # healthcheck
    if not any(t.upper().startswith("HEALTHCHECK ") and "NONE" not in t.upper() for _, t in instr):
        final_base = next((r for n, r, internal in reversed(bases) if not internal), "")
        port = next((m.group(1) for _, t in last if (m := re.match(r"EXPOSE\s+(\d+)", t, re.I))), None)
        can_fix = image_base(split_image(final_base)[0]) == "python" and port is not None
        out.append(mk("DF-HEALTHCHECK", "MEDIUM", "dockerfile", path, "No HEALTHCHECK defined",
                      "No HEALTHCHECK instruction found",
                      "Without a health check, Docker cannot tell a hung container from a healthy one, so automatic restarts have nothing to act on.",
                      "Add a HEALTHCHECK" + (f" (a TCP check on port {port} works with the Python base image)." if can_fix
                                             else " that probes your service (the right command depends on your app)."),
                      CONFIRM_REQUIRED if can_fix else MANUAL_ONLY, line=froms[-1][0], port=port))

    # package installation hygiene
    for n, t in instr:
        if re.search(r"\bapt(-get)?\s+install\b", t):
            if "--no-install-recommends" not in t:
                out.append(mk("DF-APT-RECOMMENDS", "LOW", "dockerfile", path,
                              "apt install pulls recommended packages",
                              f"line {n}: apt install without --no-install-recommends",
                              "Recommended packages bloat the image with software the app never uses.",
                              "Add --no-install-recommends.", SAFE_AUTO, line=n))
            if "/var/lib/apt/lists" not in t:
                out.append(mk("DF-APT-CLEAN", "LOW", "dockerfile", path,
                              "apt package lists are not removed in the same layer",
                              f"line {n}: no `rm -rf /var/lib/apt/lists/*`",
                              "The cached package index stays in the layer and inflates the image.",
                              "Append `&& rm -rf /var/lib/apt/lists/*` to the same RUN.", MANUAL_ONLY, line=n))
        if re.search(r"\bpip3?\s+install\b", t) and "--no-cache-dir" not in t and "PIP_NO_CACHE_DIR" not in content:
            out.append(mk("DF-PIP-CACHE", "LOW", "dockerfile", path, "pip cache is kept in the image",
                          f"line {n}: pip install without --no-cache-dir",
                          "pip's download cache is dead weight in a runtime image.",
                          "Add --no-cache-dir.", SAFE_AUTO, line=n))
        if re.search(r"\b(apt(-get)?\s+install|apk\s+add)\b.*\b(gcc|g\+\+|build-essential|make|cmake)\b", t) and len(froms) == 1:
            out.append(mk("DF-BUILD-TOOLS", "MEDIUM", "dockerfile", path,
                          "Compilers/build tools are installed in a single-stage image",
                          f"line {n}: installs a compiler toolchain",
                          "Build tools stay in the final image, enlarging it and widening the attack surface.",
                          "Use a multi-stage build: compile in a builder stage, copy artifacts into a slim runtime stage.",
                          MANUAL_ONLY, line=n))

    # ENV secrets
    for n, t in instr:
        m = re.match(r"(?:ENV|ARG)\s+([A-Za-z0-9_]+)(?:=|\s+)(\S+)", t, re.I)
        if m and SECRET_NAME.search(m.group(1)) and m.group(2).strip("'\"") and not m.group(2).startswith("$"):
            out.append(mk("CFG-SECRET", "HIGH", "configuration", path, "Credential-like value hardcoded in Dockerfile",
                          f"line {n}: {m.group(1)}=<redacted>",
                          "Values baked into image layers can be extracted by anyone who can pull the image.",
                          "Remove it from the image and inject it at runtime (env var / secret).", MANUAL_ONLY, line=n))

    # multistage opportunity
    if len(froms) == 1 and re.search(r"\b(npm (run )?build|yarn build|go build|mvn |gradle |cargo build)\b", content):
        out.append(mk("DF-MULTISTAGE", "LOW", "dockerfile", path, "Build and runtime share one stage",
                      "Build commands present in a single-stage Dockerfile",
                      "Build artifacts and toolchains remain in the shipped image.",
                      "Split into builder and runtime stages.", MANUAL_ONLY))
    return out
