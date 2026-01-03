"""I/O utilities for reading and writing JSON files."""

import json
import os
from typing import Any


def read_json(path: str) -> Any:
    """Read and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any, indent: int = 2) -> None:
    """Write data to a JSON file with pretty formatting."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def read_text(path: str) -> str:
    """Read a text file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str) -> None:
    """Write content to a text file."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_dir(path: str) -> None:
    """Ensure a directory exists."""
    os.makedirs(path, exist_ok=True)


def list_case_dirs(cases_dir: str) -> list:
    """List all case directories sorted by name."""
    if not os.path.exists(cases_dir):
        return []
    dirs = []
    for name in os.listdir(cases_dir):
        case_path = os.path.join(cases_dir, name)
        if os.path.isdir(case_path):
            dirs.append(case_path)
    return sorted(dirs)
