from __future__ import annotations

from typing import Callable, Optional, Tuple
from app.modules.device_management.models.device_model import DeviceModel

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil might be unavailable
    psutil = None


DeviceCountProvider = Callable[[], Tuple[Optional[int], Optional[int]]]


class PerformanceStatusService:

    def __init__(self, device_provider: Optional[DeviceCountProvider] = None) -> None:
        self._device_provider = device_provider or self._default_device_provider
        self._device_model: Optional[DeviceModel] = None

    def set_device_provider(self, provider: DeviceCountProvider) -> None:
        self._device_provider = provider

    def set_device_model(self, model: DeviceModel) -> None:
        self._device_model = model

    def collect_summary(self) -> dict:
        online, total = self._collect_device_counts()
        return {
            "cpu_percent": self._collect_cpu_percent(),
            "memory_usage": self._collect_memory_usage(),
            "device_online": online,
            "device_total": total,
        }

    def _collect_cpu_percent(self) -> Optional[float]:
        if psutil is None:
            return None
        try:
            return float(psutil.cpu_percent(interval=None))
        except Exception:
            return None

    def _collect_memory_usage(self) -> Optional[str]:
        if psutil is None:
            return None
        try:
            virtual = psutil.virtual_memory()
        except Exception:
            return None
        total_gb = virtual.total / (1024 ** 3)
        used_gb = (virtual.total - virtual.available) / (1024 ** 3)
        return f"{used_gb:.1f}/{total_gb:.1f}GB ({virtual.percent:.0f}%)"

    def _collect_device_counts(self) -> Tuple[Optional[int], Optional[int]]:
        if not self._device_provider:
            return None, None
        try:
            return self._device_provider()
        except Exception:
            return None, None

    def _default_device_provider(self) -> Tuple[Optional[int], Optional[int]]:
        if not self._device_model:
            return None, None
        total = len(getattr(self._device_model, "devices", []) or [])
        online = sum(1 for d in getattr(self._device_model, "devices", []) if "✅" in d.get("status", ""))
        return online, total
