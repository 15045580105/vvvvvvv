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
        self._parsers: dict[str, DPTParser] = {}
        self._current_path: Optional[str] = None

        cached_path = self._repository.load_last_path()
        if cached_path:
            try:
                self.load_from_file(cached_path, persist=False)
            except Exception:
                # Ignore cached load failures; user can re-import
                self._parser = None
                self._parsers = {}
                self._current_path = None

    def load_from_file(self, file_path: str, persist: bool = True) -> None:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"DPT file not found: {path}")

        self._load_parsers_from_file(path)
        self._current_path = str(path)

        if persist:
            self._repository.save_last_path(str(path))

    def parse_bytes(self, payload: bytes, did: Optional[str] = None) -> Optional[DPTParseResult]:
        # Try to find specific parser for DID
        if did:
            # Normalize DID (remove 0x, uppercase)
            did_key = did.strip().upper().replace("0X", "")
            if did_key in self._parsers:
                return self._parsers[did_key].parse_bytes(payload)
            # Try with 0x prefix if not found
            if f"0X{did_key}" in self._parsers:
                return self._parsers[f"0X{did_key}"].parse_bytes(payload)

        # Fallback to default parser if available
        if self._parser:
            return self._parser.parse_bytes(payload)

        return None

    def _load_parsers_from_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unsupported DPT format in {path}") from exc

        self._parser = None
        self._parsers = {}

        if isinstance(data, list):
            # Single definition list
            self._parser = DPTParser.from_dict_config({"fields": data})
        elif isinstance(data, dict):
            if "fields" in data:
                # Single definition dict
                self._parser = DPTParser.from_dict_config(data)
            else:
                # Assume dict of DID -> definition
                for key, value in data.items():
                    # Normalize key to upper case for case-insensitive lookup
                    did_key = key.strip().upper().replace("0X", "")

                    if isinstance(value, list):
                        config = {"fields": value}
                    elif isinstance(value, dict):
                        if "data_format" in value:
                            config = value["data_format"]
                        else:
                            config = value
                    else:
                        continue

                    try:
                        parser = DPTParser.from_dict_config(config)
                        # Store description if available in the DID definition
                        if isinstance(value, dict) and "description" in value:
                            parser.description = value["description"]
                        self._parsers[did_key] = parser
                        # Also store with 0X prefix just in case
                        # self._parsers[f"0X{did_key}"] = self._parsers[did_key]
                    except Exception:
                        pass
        else:
            raise ValueError(f"Unsupported DPT structure: {type(data).__name__}")

    @property
    def current_path(self) -> Optional[str]:
        return self._current_path

    def is_ready(self) -> bool:
        return self._parser is not None or bool(self._parsers)

