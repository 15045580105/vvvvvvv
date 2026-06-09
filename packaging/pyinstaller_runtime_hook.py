"""Runtime setup for the packaged VCC application.

The 64-bit application must not globally switch PATH/PYTHONHOME to the bundled
32-bit runtime.  This hook only exposes stable environment variables so code
that needs to call a 32-bit DLL can spawn the bundled 32-bit python.exe with an
isolated child-process environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _set_if_exists(name: str, path: Path) -> None:
    if path.exists():
        os.environ.setdefault(name, str(path))


base_dir = _base_dir()
runtime32_home = base_dir / "runtime32"
runtime32_exe = runtime32_home / "python.exe"

os.environ.setdefault("VCC_APP_ROOT", str(base_dir))
_set_if_exists("VCC_RUNTIME32_HOME", runtime32_home)
_set_if_exists("PYTHON32_HOME", runtime32_home)
_set_if_exists("PYTHON_32BIT", runtime32_exe)
_set_if_exists("VCC_PYTHON32_EXE", runtime32_exe)

# Intentionally do NOT prepend runtime32 to this 64-bit process PATH.
# 32-bit DLL calls must run in a 32-bit child process and receive their own PATH.

