from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Return the application root for both source and PyInstaller builds."""
    env_root = os.environ.get("VCC_APP_ROOT")
    if env_root:
        return Path(env_root).resolve()

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS).resolve()

        exe_dir = Path(sys.executable).resolve().parent
        internal_dir = exe_dir / "_internal"
        return internal_dir if internal_dir.exists() else exe_dir

    return Path(__file__).resolve().parents[3]


def resource_path(*parts: str) -> str:
    """Build an absolute path to a bundled resource."""
    return str(app_root().joinpath(*parts))


def image_path(filename: str) -> str:
    """Build an absolute path to a bundled image resource."""
    return resource_path("app", "resources", "images", filename)


def qss_url(path: str) -> str:
    """Return a Qt stylesheet url() compatible with Windows paths."""
    return Path(path).resolve().as_posix()
