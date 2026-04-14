"""Compatibility export for ssh_manager from project root."""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOT_MODULE_PATH = PROJECT_ROOT / "ssh_manager.py"

_spec = importlib.util.spec_from_file_location("root_ssh_manager", ROOT_MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load module from {ROOT_MODULE_PATH}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

for _name, _value in vars(_module).items():
    if not _name.startswith("_"):
        globals()[_name] = _value

