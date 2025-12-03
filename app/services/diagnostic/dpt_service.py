from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.common.utils.DPTUtils import DPTParser, DPTParseResult
from app.common.repositories.dpt_repository import DPTRepository


class DPTService:
    """Manage loading and parsing of DPT definition files."""

    def __init__(self, repository: Optional[DPTRepository] = None) -> None:
        self._repository = repository or DPTRepository()
        self._parser: Optional[DPTParser] = None
        self._current_path: Optional[str] = None

        cached_path = self._repository.load_last_path()
        if cached_path:
            try:
                self.load_from_file(cached_path, persist=False)
            except Exception:
                # Ignore cached load failures; user can re-import
                self._parser = None
                self._current_path = None

    def load_from_file(self, file_path: str, persist: bool = True) -> None:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"DPT file not found: {path}")

        parser = self._build_parser_from_file(path)
        self._parser = parser
        self._current_path = str(path)

        if persist:
            self._repository.save_last_path(str(path))

    def parse_bytes(self, payload: bytes) -> Optional[DPTParseResult]:
        if not self._parser:
            return None
        return self._parser.parse_bytes(payload)

    def _build_parser_from_file(self, path: Path) -> DPTParser:
        text = path.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unsupported DPT format in {path}") from exc

        if isinstance(data, dict):
            config = data
        elif isinstance(data, list):
            config = {"fields": data}
        else:
            raise ValueError(f"Unsupported DPT structure: {type(data).__name__}")

        return DPTParser.from_dict_config(config)

    @property
    def current_path(self) -> Optional[str]:
        return self._current_path

    def is_ready(self) -> bool:
        return self._parser is not None

