"""Dependency manifest rules (requirements*.txt, package.json)."""

from __future__ import annotations

import json
import re

from ..models import CONFIRM_REQUIRED, MANUAL_ONLY
from .common import mk

DEV_PY = {"pytest", "pytest-cov", "pytest-asyncio", "black", "flake8", "mypy", "pylint", "ruff", "isort",
          "ipython", "ipdb", "tox", "coverage", "pre-commit", "sphinx", "jupyter", "notebook", "bandit"}
HEAVY_PY = {"torch": "PyTorch", "tensorflow": "TensorFlow", "tensorflow-gpu": "TensorFlow", "jax": "JAX",
            "opencv-python": "OpenCV (full, non-headless)", "scipy": "SciPy", "transformers": "Transformers"}
NATIVE_PY = {"psycopg2": "libpq headers + a compiler (psycopg2-binary avoids this)", "lxml": "libxml2/libxslt headers",
             "pycurl": "libcurl headers", "mysqlclient": "MySQL client headers + a compiler",
             "cryptography": None, "pillow": None, "grpcio": None}
DEV_JS = {"jest", "mocha", "eslint", "prettier", "nodemon", "typescript", "webpack", "vite", "ts-node",
          "@types/node", "chai", "cypress", "playwright", "storybook"}
MANY = 40


def _req_lines(content):
    for i, raw in enumerate(content.splitlines(), 1):
        s = raw.split("#", 1)[0].strip()
        if not s or s.startswith(("-", "git+", "http")):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$", s)
        if m:
            yield i, m.group(1).lower().replace("_", "-"), m.group(3).split(";")[0].strip()


def analyze_requirements(path: str, content: str):
    out, pkgs = [], list(_req_lines(content))
    if not pkgs:
        return out
    unpinned = [p for _, p, spec in pkgs if not spec]
    loose = [p for _, p, spec in pkgs if spec and "==" not in spec]
    if unpinned:
        out.append(mk("DEP-UNPINNED", "MEDIUM", "dependencies", path,
                      f"{len(unpinned)} dependenc{'y is' if len(unpinned) == 1 else 'ies are'} unpinned",
                      "No version specifier: " + ", ".join(unpinned[:6]) + ("…" if len(unpinned) > 6 else ""),
                      "Unpinned dependencies resolve to different versions on each build, so edge nodes can diverge.",
                      "Pin exact versions (pip freeze) or use a lock file.", MANUAL_ONLY))
    elif loose:
        out.append(mk("DEP-LOOSE", "LOW", "dependencies", path, f"{len(loose)} dependencies use version ranges, not exact pins",
                      "Ranges: " + ", ".join(loose[:6]), "Ranges can drift between builds.", "Pin with == or use a lock file.", MANUAL_ONLY))
    dev = [(i, p) for i, p, _ in pkgs if p in DEV_PY]
    if dev and not re.search(r"dev|test", path.lower()):
        out.append(mk("DEP-DEV-IN-PROD", "LOW", "dependencies", path,
                      f"Development tools listed in a production manifest ({len(dev)})",
                      "Dev packages: " + ", ".join(p for _, p in dev),
                      "Test/lint tooling adds image size and attack surface without being used at runtime.",
                      "Move them to a separate requirements-dev.txt.", CONFIRM_REQUIRED, line=dev[0][0],
                      remove_lines=[i for i, _ in dev]))
    heavy = [(p, HEAVY_PY[p]) for _, p, _ in pkgs if p in HEAVY_PY]
    if heavy:
        out.append(mk("DEP-HEAVY", "LOW", "dependencies", path, "Large dependencies present",
                      "Known large packages: " + ", ".join(n for _, n in heavy),
                      "These packages ship very large wheels, which matters for image size and edge bandwidth.",
                      "Check whether a lighter alternative (e.g. opencv-python-headless, CPU-only wheels) suffices.", MANUAL_ONLY))
    native = [(p, NATIVE_PY[p]) for _, p, _ in pkgs if NATIVE_PY.get(p)]
    if native:
        out.append(mk("DEP-NATIVE", "LOW", "dependencies", path, "Dependencies that need native build tooling",
                      "; ".join(f"{p}: {n}" for p, n in native),
                      "Compiling native extensions on the image pulls in toolchains and can fail on ARM edge nodes.",
                      "Prefer prebuilt wheels (e.g. psycopg2-binary) or build in a multi-stage Dockerfile.", MANUAL_ONLY))
    if len(pkgs) > MANY:
        out.append(mk("DEP-MANY", "LOW", "dependencies", path, f"{len(pkgs)} dependencies declared",
                      f"{len(pkgs)} entries (threshold {MANY})", "Every dependency increases image size and update burden.",
                      "Audit for unused packages.", MANUAL_ONLY))
    return out


def analyze_package_json(path: str, content: str):
    out = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return [mk("CFG-MALFORMED", "HIGH", "configuration", path, "package.json is not valid JSON",
                   f"line {exc.lineno}: {exc.msg}", "Builds will fail and the dependencies cannot be analysed.",
                   "Fix the JSON syntax.", MANUAL_ONLY, line=exc.lineno)]
    if not isinstance(data, dict):
        return out
    deps = data.get("dependencies") or {}
    if not isinstance(deps, dict):
        return out
    loose = [k for k, v in deps.items() if str(v).strip() in ("*", "latest", "")]
    if loose:
        out.append(mk("DEP-UNPINNED", "MEDIUM", "dependencies", path, f"{len(loose)} dependencies use `*`/`latest`",
                      ", ".join(loose[:6]), "Builds are not reproducible.", "Pin versions.", MANUAL_ONLY))
    dev = [k for k in deps if k in DEV_JS]
    if dev:
        out.append(mk("DEP-DEV-IN-PROD", "LOW", "dependencies", path, "Development tools in `dependencies`",
                      ", ".join(dev), "They are installed into production images.", "Move to devDependencies.", MANUAL_ONLY))
    if len(deps) > MANY:
        out.append(mk("DEP-MANY", "LOW", "dependencies", path, f"{len(deps)} dependencies declared", f"{len(deps)} entries",
                      "Every dependency increases image size.", "Audit for unused packages.", MANUAL_ONLY))
    return out
