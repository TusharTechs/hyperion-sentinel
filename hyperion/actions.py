"""SSE framing and the IDE action protocol (reverse-engineered from the IDE frontend).

The IDE executes any SSE `data:` payload that is a JSON object with an `action` key:
create_file / edit_file / delete_file / create_folder / delete_folder / write_yaml_to_editor.
Plain text goes in {"response": "<increment>"}.
"""

from __future__ import annotations

import json

from .workspace import safe_path


def sse(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def text(s: str) -> str:
    return sse({"response": s})


DONE = "data: [DONE]\n\n"


def create_file(path: str, content: str) -> str:
    return sse({"action": "create_file", "path": safe_path(path), "content": content})


def edit_file(path: str, content: str) -> str:
    return sse({"action": "edit_file", "path": safe_path(path), "content": content})


def delete_file(path: str) -> str:
    return sse({"action": "delete_file", "path": safe_path(path)})


def delete_folder(path: str) -> str:
    return sse({"action": "delete_folder", "path": safe_path(path)})


def create_folder(path: str) -> str:
    return sse({"action": "create_folder", "path": safe_path(path)})
