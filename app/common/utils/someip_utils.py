from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import openpyxl

from app.common.utils.path_utils import get_device_config_path
from app.services.system.config_service import ConfigService


class SomeIPMatrixError(Exception):
    """SomeIP matrix parsing error."""


class SomeIPMatrixStore:
    """Parse and cache SomeIP Deployment sheet lookups.

    Contract:
    - Input: explicit matrix Excel path, or the path saved by the SomeIP settings UI.
    - Cache: in-memory + JSON cache file keyed by matrix file mtime/size.
    - Query: service_id + instance_id -> Service Interface Name.
    """

    CACHE_NAME = "someip_matrix_cache"
    DEPLOYMENT_SHEET_NAME = "Deployment"

    def __init__(self) -> None:
        self._config_service = ConfigService()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

    def import_matrix(self, file_path: Optional[str] = None, force_reload: bool = False) -> Dict[str, Any]:
        matrix_path = self.resolve_matrix_path(file_path)
        fingerprint = self._build_fingerprint(matrix_path)
        memory_key = str(matrix_path)

        if not force_reload:
            cached = self._memory_cache.get(memory_key)
            if cached and cached.get("fingerprint") == fingerprint:
                return cached

            disk_cache = self._load_disk_cache()
            cache_entry = disk_cache.get(memory_key)
            if cache_entry and cache_entry.get("fingerprint") == fingerprint:
                self._memory_cache[memory_key] = cache_entry
                return cache_entry

        parsed = self._parse_matrix_file(matrix_path)
        payload = {
            "matrix_path": str(matrix_path),
            "fingerprint": fingerprint,
            "services": parsed,
            "count": len(parsed),
        }
        self._memory_cache[memory_key] = payload

        disk_cache = self._load_disk_cache()
        disk_cache[memory_key] = payload
        self._save_disk_cache(disk_cache)
        return payload

    def get_service_interface_name(
        self,
        service_id: Any,
        instance_id: Any,
        file_path: Optional[str] = None,
        default: str = "Unknown Service",
    ) -> str:
        try:
            cache = self.import_matrix(file_path=file_path)
        except Exception:
            return default
        lookup_key = self._build_lookup_key(service_id, instance_id)
        item = cache.get("services", {}).get(lookup_key)
        if item:
            return item.get("service_interface_name") or default
        return default

    def get_service_info(
        self,
        service_id: Any,
        instance_id: Any,
        file_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            cache = self.import_matrix(file_path=file_path)
        except Exception:
            return None
        return cache.get("services", {}).get(self._build_lookup_key(service_id, instance_id))

    def resolve_matrix_path(self, file_path: Optional[str] = None) -> Path:
        candidates: List[Path] = []
        if file_path:
            candidates.append(Path(file_path))

        settings = self._load_app_settings().get("someip", {})
        configured = settings.get("matrix_file")
        if configured:
            candidates.append(Path(configured))

        for candidate in candidates:
            if candidate and candidate.exists() and candidate.is_file():
                return candidate.resolve()

        raise FileNotFoundError("未找到 SomeIP 矩阵表文件，请先在 SomeIP 设置界面中导入矩阵 Excel 文件。")

    def _parse_matrix_file(self, file_path: Path) -> Dict[str, Dict[str, Any]]:
        workbook = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        try:
            if self.DEPLOYMENT_SHEET_NAME not in workbook.sheetnames:
                raise SomeIPMatrixError(f"矩阵缺少 `{self.DEPLOYMENT_SHEET_NAME}` sheet")

            sheet = workbook[self.DEPLOYMENT_SHEET_NAME]
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                return {}

            header_row_index = self._find_header_row_index(rows)
            headers = [self._normalize_header(v) for v in rows[header_row_index]]

            service_id_idx = self._find_col_idx(headers, [
                "service id", "serviceid", "service_identifier", "service identifier"
            ])
            instance_id_idx = self._find_col_idx(headers, [
                "instance id", "instanceid", "instance identifier", "instance_identifier"
            ])
            interface_name_idx = self._find_col_idx(headers, [
                "service interface name", "serviceinterface name", "service interface", "interface name"
            ])

            missing = []
            if service_id_idx < 0:
                missing.append("Service ID")
            if instance_id_idx < 0:
                missing.append("Instance ID")
            if interface_name_idx < 0:
                missing.append("Service Interface Name")
            if missing:
                raise SomeIPMatrixError(f"Deployment sheet 缺少关键列: {', '.join(missing)}")

            services: Dict[str, Dict[str, Any]] = {}
            for row in rows[header_row_index + 1:]:
                service_id_raw = self._safe_row_get(row, service_id_idx)
                instance_id_raw = self._safe_row_get(row, instance_id_idx)
                interface_name = self._safe_row_get(row, interface_name_idx)

                normalized_service_id = self._normalize_id(service_id_raw)
                normalized_instance_id = self._normalize_id(instance_id_raw)
                if not normalized_service_id or not normalized_instance_id or not interface_name:
                    continue

                lookup_key = self._build_lookup_key(normalized_service_id, normalized_instance_id)
                services[lookup_key] = {
                    "service_id": normalized_service_id,
                    "instance_id": normalized_instance_id,
                    "service_interface_name": interface_name,
                }

            return services
        finally:
            workbook.close()

    def _find_header_row_index(self, rows: List[Tuple[Any, ...]], max_scan: int = 20) -> int:
        best_index = 0
        best_score = -1
        for idx, row in enumerate(rows[:max_scan]):
            headers = [self._normalize_header(cell) for cell in row]
            score = 0
            if self._find_col_idx(headers, ["service id", "serviceid"]) >= 0:
                score += 2
            if self._find_col_idx(headers, ["instance id", "instanceid"]) >= 0:
                score += 2
            if self._find_col_idx(headers, ["service interface name", "interface name"]) >= 0:
                score += 2
            if any(headers):
                score += 1
            if score > best_score:
                best_score = score
                best_index = idx
        return best_index

    @staticmethod
    def _find_col_idx(headers: Iterable[str], keywords: Iterable[str]) -> int:
        for idx, header in enumerate(headers):
            if any(keyword in header for keyword in keywords):
                return idx
        return -1

    @staticmethod
    def _normalize_header(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).replace("\n", " ").replace("\t", " ").split()).strip().lower()

    @staticmethod
    def _safe_row_get(row: Tuple[Any, ...], idx: int) -> str:
        if idx < 0 or idx >= len(row):
            return ""
        value = row[idx]
        return "" if value is None else str(value).strip()

    @classmethod
    def _build_lookup_key(cls, service_id: Any, instance_id: Any) -> str:
        normalized_service_id = cls._normalize_id(service_id)
        normalized_instance_id = cls._normalize_id(instance_id)
        return f"{normalized_service_id}:{normalized_instance_id}"

    @staticmethod
    def _normalize_id(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, int):
            return f"0x{value:04X}"
        if isinstance(value, float):
            if value.is_integer():
                return f"0x{int(value):04X}"
            return ""

        text = str(value).strip()
        if not text:
            return ""
        compact = text.replace("_", "").replace(" ", "")
        try:
            if compact.lower().startswith("0x"):
                return f"0x{int(compact, 16):04X}"
            return f"0x{int(compact, 10):04X}"
        except ValueError:
            return text.upper()

    @staticmethod
    def _build_fingerprint(file_path: Path) -> Dict[str, Any]:
        stat = file_path.stat()
        return {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        }

    def _cache_file_path(self) -> Path:
        return Path(get_device_config_path()) / f"{self.CACHE_NAME}.json"

    def _load_disk_cache(self) -> Dict[str, Any]:
        data = self._config_service.load_json(self.CACHE_NAME, default={})
        return data if isinstance(data, dict) else {}

    def _save_disk_cache(self, data: Dict[str, Any]) -> None:
        self._config_service.save_json(self.CACHE_NAME, data)

    def _load_app_settings(self) -> Dict[str, Any]:
        data = self._config_service.load_json("app_settings", default={})
        return data if isinstance(data, dict) else {}


_default_store = SomeIPMatrixStore()


def import_someip_matrix(file_path: Optional[str] = None, force_reload: bool = False) -> Dict[str, Any]:
    return _default_store.import_matrix(file_path=file_path, force_reload=force_reload)


def get_service_interface_name(service_id: Any, instance_id: Any, file_path: Optional[str] = None, default: str = "Unknown Service") -> str:
    return _default_store.get_service_interface_name(service_id, instance_id, file_path=file_path, default=default)


def get_service_info(service_id: Any, instance_id: Any, file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _default_store.get_service_info(service_id, instance_id, file_path=file_path)
