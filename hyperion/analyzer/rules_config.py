"""Secret / configuration hygiene rules, run over every text file."""

from __future__ import annotations

import posixpath
import re

from ..models import MANUAL_ONLY, SAFE_AUTO
from .common import kind_of_file, mk

PLACEHOLDER = re.compile(r"^(<.*>|\$\{.*\}|\$[A-Z_]+|changeme|change-me|your[-_ ].*|xxx+|\*+|todo|example.*|null|none|false|true|)$", re.I)
SECRET_KEY = re.compile(r"(pass(word|wd)?|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|auth[_-]?key|credentials?)$", re.I)
ASSIGN = re.compile(r"""^\s*(?:export\s+)?["']?([A-Za-z0-9_.\-]+)["']?\s*[:=]\s*["']?([^"'\s#][^"'#]*?)["']?\s*(?:#.*)?$""")
TOKEN_PATTERNS = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "CRITICAL"),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "CRITICAL"),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "CRITICAL"),
    ("API key (sk-… style)", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "HIGH"),
    ("Slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b"), "HIGH"),
]
URL = re.compile(r"https?://([A-Za-z0-9.\-]+)(?::\d+)?[^\s\"'<>)]*")
URL_OK = ("localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org", "w3.org", "json-schema.org",
          "schemas.", "github.com", "gitlab.", "hyper-ai-project.eu", "docker.io", "kubernetes.io", "k8s.io")
SOURCE_EXT = (".py", ".js", ".ts", ".env", ".ini", ".cfg", ".toml", ".json", ".conf")
TEMPLATE_NAME = re.compile(r"(\.example|\.sample|\.template|\.dist)$|^example", re.I)
SKIP_NAMES = {"package-lock.json", "uv.lock", "yarn.lock", "poetry.lock"}


def analyze_secrets(path: str, content: str):
    name = posixpath.basename(path)
    if name in SKIP_NAMES or TEMPLATE_NAME.search(name):
        return []
    hits: list[tuple[int, str, str]] = []  # (line, sev, label)
    is_dockerfile = kind_of_file(path) in ("dockerfile", "compose")  # handled by their own rule modules
    for i, line in enumerate(content.splitlines(), 1):
        if len(line) > 2000:
            continue
        for label, rx, sev in TOKEN_PATTERNS:
            if rx.search(line):
                hits.append((i, sev, label))
        if is_dockerfile:
            continue
        m = ASSIGN.match(line)
        if m and SECRET_KEY.search(m.group(1)) and not PLACEHOLDER.match(m.group(2).strip()) and len(m.group(2).strip()) >= 4:
            if re.search(r"(os\.environ|getenv|process\.env|\{\{|\$\{)", line):
                continue
            hits.append((i, "HIGH", f"{m.group(1)}=<redacted>"))
    out, seen = [], set()
    for ln, sev, label in hits:
        if (ln, label) in seen:
            continue
        seen.add((ln, label))
        out.append(mk("CFG-SECRET", sev, "configuration", path, "Possible hardcoded secret",
                      f"line {ln}: {label} (value redacted)",
                      "Secrets in workspace files leak through version control and images, and cannot be rotated per site.",
                      "Move the value to an environment variable or secret store and rotate it.", MANUAL_ONLY, line=ln))
    return out


def analyze_urls(files: dict[str, str]):
    """One aggregated finding for hardcoded external URLs in source/config files."""
    hits = []
    for path, content in files.items():
        if not path.lower().endswith(SOURCE_EXT) and kind_of_file(path) != "env":
            continue
        if posixpath.basename(path) in SKIP_NAMES or TEMPLATE_NAME.search(posixpath.basename(path)):
            continue
        for i, line in enumerate(content.splitlines(), 1):
            s = line.strip()
            if s.startswith(("#", "//", "*", '"""', "'''")) or "http://" not in s and "https://" not in s:
                continue
            for m in URL.finditer(line):
                host = m.group(1).lower()
                if not any(host == ok or host.endswith("." + ok.strip(".")) or host.startswith(ok) for ok in URL_OK):
                    hits.append((path, i, host))
    if not hits:
        return []
    ex = "; ".join(f"{p}:{ln} → {h}" for p, ln, h in hits[:4])
    return [mk("CFG-EXTERNAL-URL", "LOW", "configuration", hits[0][0],
               f"{len(hits)} hardcoded external URL(s) in source/config",
               ex + ("…" if len(hits) > 4 else ""),
               "Hardcoded endpoints break when a site is offline, behind a proxy, or moved; edge deployments need them configurable.",
               "Read endpoints from environment/config.", MANUAL_ONLY, line=hits[0][1])]


def analyze_env_template(files: dict[str, str]):
    names = {posixpath.basename(p): p for p in files}
    env_files = [p for p in files if posixpath.basename(p) == ".env"]
    out = []
    for envp in env_files:
        folder = posixpath.dirname(envp)
        tmpl = [n for n in (".env.example", ".env.sample", ".env.template") if posixpath.join(folder, n) in files]
        if not tmpl:
            keys = [m.group(1) for ln in files[envp].splitlines() if (m := re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", ln))]
            out.append(mk("CFG-NO-ENV-TEMPLATE", "LOW", "configuration", envp, "`.env` has no committed template (.env.example)",
                          f"{len(keys)} variable(s) in .env, no .env.example next to it",
                          "Teammates and CI cannot tell which variables the app needs to start.",
                          "Create .env.example listing the variable names with blank/dummy values.",
                          SAFE_AUTO, target=envp, folder=folder, keys=keys))
    return out
