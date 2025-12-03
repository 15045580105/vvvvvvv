from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class DPTRepository:
    """Handle persistence of the last selected DPT file path."""

    def __init__(self, cache_file: Optional[Path] = None) -> None:
        if cache_file is None:
            project_root = Path(__file__).resolve().parents[4]
            cache_file = project_root / "app" / "data" / "did_dpt_cache.json"
        self._cache_file = cache_file

    def save_last_path(self, file_path: str) -> None:
        data = {"last_path": file_path}
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_last_path(self) -> Optional[str]:
        if not self._cache_file.exists():
            return None
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        last_path = data.get("last_path")
        return str(last_path) if last_path else None

