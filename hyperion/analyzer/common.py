"""Shared helpers for analyzer rule modules."""

from __future__ import annotations

import io
import posixpath
import re

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ..models import Finding, MANUAL_ONLY

# Conservative, well-known stable tags used when pinning `latest`. Pinning is only ever
# offered for images in this table; anything else is MANUAL_ONLY (we never invent a tag).
KNOWN_TAGS = {
    "nginx": "1.27-alpine", "python": "3.12-slim", "node": "20-alpine", "redis": "7-alpine",
    "postgres": "16-alpine", "alpine": "3.20", "ubuntu": "24.04", "debian": "12-slim", "busybox": "1.36",
    "golang": "1.22-alpine", "mysql": "8.0", "mongo": "7.0", "httpd": "2.4-alpine", "eclipse-mosquitto": "2",
    "rabbitmq": "3-alpine", "memcached": "1.6-alpine",
}
# Images where a slimmer variant of the same version is a drop-in choice.
FULL_VARIANTS = {"python", "node", "golang", "ubuntu", "debian"}

_yaml = YAML(typ="rt")
_yaml.preserve_quotes = True
_yaml.width = 4096


def yaml_loader() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_yaml_docs(content: str):
    """Return (docs, error). `error` is (line, message) when YAML is malformed."""
    try:
        docs = [d for d in yaml_loader().load_all(content) if d is not None]
        return docs, None
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (mark.line + 1) if mark is not None else None
        msg = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        return [], (line, str(msg))
    except Exception as exc:  # pragma: no cover - ruamel raises assorted errors on odd input
        return [], (None, f"{type(exc).__name__}: {exc}")


def line_of(node, key=None) -> int | None:
    """1-based line of a ruamel node (or of one key inside it)."""
    try:
        if key is not None:
            return node.lc.key(key)[0] + 1
        return node.lc.line + 1
    except Exception:
        return None


def is_map(x) -> bool:
    return hasattr(x, "items") and hasattr(x, "get")


def split_image(ref: str) -> tuple[str, str | None]:
    """'docker.io/library/nginx:1.2' -> ('docker.io/library/nginx', '1.2'). Digests count as pinned."""
    ref = str(ref).strip()
    if "@sha256:" in ref:
        return ref.split("@")[0], "@digest"
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        name, tag = ref.rsplit(":", 1)
        return name, tag
    return ref, None


def image_base(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def is_unpinned(tag: str | None) -> bool:
    return tag is None or tag.lower() == "latest"


def pin_suggestion(ref: str) -> str | None:
    name, _tag = split_image(ref)
    base = image_base(name)
    if base in KNOWN_TAGS:
        return f"{name}:{KNOWN_TAGS[base]}"
    return None


def kind_of_file(path: str) -> str:
    n = posixpath.basename(path).lower()
    if n == "dockerfile" or n.startswith("dockerfile.") or n.endswith(".dockerfile"):
        return "dockerfile"
    if n in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") or re.match(
        r"^docker-compose\..+\.ya?ml$", n
    ):
        return "compose"
    if n.endswith((".yaml", ".yml")):
        return "yaml"
    if re.match(r"^requirements.*\.txt$", n):
        return "requirements"
    if n == "package.json":
        return "package_json"
    if n == ".dockerignore":
        return "dockerignore"
    if n.startswith(".env"):
        return "env"
    return "other"


def mk(rule, sev, cat, file, finding, evidence, why, fix, safety=MANUAL_ONLY, line=None, end_line=None, **fixparams):
    return Finding(rule=rule, severity=sev, category=cat, file=file, finding=finding, evidence=evidence,
                   why_it_matters=why, recommended_fix=fix, automation_safety=safety, line=line,
                   end_line=end_line, fix=fixparams)
