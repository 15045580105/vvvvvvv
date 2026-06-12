from __future__ import annotations

from typing import Callable, Optional, Tuple
from app.modules.device_management.models.device_model import DeviceModel

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil might be unavailable
    psutil = None

import sys
import ctypes
from ctypes import wintypes
import time

_kernel32 = None
if sys.platform.startswith("win"):
    try:
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except Exception:
        _kernel32 = None

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
        protocol_status = self._collect_protocol_status()
        return {
            "cpu_percent": self._collect_cpu_percent(),
            "memory_usage": self._collect_memory_usage(),
            "device_online": online,
            "device_total": total,
            "protocol_status": protocol_status,
        }

    def _collect_protocol_status(self) -> dict:
        status = {
            "ssh": "离线",
            "doip": "离线",
            "someip": "离线",
            "doip_device": None,
            "ssh_device": None,
            "someip_device": None,
        }
        if not self._device_model:
            return status

        from app.modules.device_management.models.device_model import ONLINE

        devices = getattr(self._device_model, "devices", []) or []

        for idx, d in enumerate(devices, start=1):
            device_label = str(idx)
            ssh_st = str(d.get("ssh_connect_status", ""))
            doip_st = str(d.get("doip_connect_status", ""))
            someip_st = str(d.get("someip_connect_status", ""))

            if "建链成功" in ssh_st or "在线" in ssh_st:
                status["ssh"] = "在线"
                status["ssh_device"] = device_label
            if "建链成功" in doip_st or "在线" in doip_st:
                status["doip"] = "在线"
                status["doip_device"] = device_label
            if "建链成功" in someip_st or "在线" in someip_st:
                status["someip"] = "在线"
                status["someip_device"] = device_label

        return status

    def _collect_cpu_percent(self) -> Optional[float]:
        # Prefer psutil when available; sample briefly to avoid returning 0.0 on first call
        if psutil is not None:
            try:
                return float(psutil.cpu_percent(interval=0.1))
            except Exception:
                pass

        # Windows fallback via GetSystemTimes
        try:
            if sys.platform.startswith("win"):
                return self._cpu_percent_windows()
        except Exception:
            pass
        return None

    def _cpu_percent_windows(self) -> Optional[float]:
        """Compute CPU usage percent on Windows using GetSystemTimes.
        Returns a percentage over a short sampling window.
        """
        try:
            kernel1, user1, idle1 = self._get_system_times()
            time.sleep(0.1)
            kernel2, user2, idle2 = self._get_system_times()
        except Exception:
            return None

        # Note: kernel time includes idle time, subtract idle from kernel
        kernel_delta = kernel2 - kernel1
        user_delta = user2 - user1
        idle_delta = idle2 - idle1
        total = (kernel_delta + user_delta)
        busy = total - idle_delta
        if total <= 0:
            return None
        percent = (busy * 100.0) / total
        # Clamp to [0, 100]
        return max(0.0, min(100.0, percent))

    def _get_system_times(self) -> Tuple[int, int, int]:
        """Return (kernel, user, idle) time values in 100-ns units as integers."""
        if _kernel32 is None:
            raise OSError("kernel32 not available")
        # Resolve function dynamically to avoid IDE resolution warnings
        GetSystemTimes = getattr(_kernel32, "GetSystemTimes", None)
        if GetSystemTimes is None:
            raise OSError("GetSystemTimes not found")
        GetSystemTimes.argtypes = [
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        GetSystemTimes.restype = wintypes.BOOL

        idle = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        if not ok:
            raise OSError("GetSystemTimes failed")

        def _to_int(ft: wintypes.FILETIME) -> int:
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        return _to_int(kernel), _to_int(user), _to_int(idle)

    def _collect_memory_usage(self) -> Optional[str]:
        if psutil is not None:
            try:
                virtual = psutil.virtual_memory()
                total_gb = virtual.total / (1024 ** 3)
                used_gb = (virtual.total - virtual.available) / (1024 ** 3)
                return f"{used_gb:.1f}/{total_gb:.1f}GB ({virtual.percent:.0f}%)"
            except Exception:
                pass

        # Windows fallback via GlobalMemoryStatusEx
        try:
            if sys.platform.startswith("win"):
                status = self._global_memory_status_ex()
                total = status["ullTotalPhys"]
                avail = status["ullAvailPhys"]
                percent = status["dwMemoryLoad"]
                total_gb = total / (1024 ** 3)
                used_gb = (total - avail) / (1024 ** 3)
                return f"{used_gb:.1f}/{total_gb:.1f}GB ({percent:.0f}%)"
        except Exception:
            pass
        return None

    def _global_memory_status_ex(self) -> dict:
        """Return a dict with memory status similar to GlobalMemoryStatusEx."""
        if _kernel32 is None:
            raise OSError("kernel32 not available")

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        GlobalMemoryStatusEx = getattr(_kernel32, "GlobalMemoryStatusEx", None)
        if GlobalMemoryStatusEx is None:
            raise OSError("GlobalMemoryStatusEx not found")
        GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
        GlobalMemoryStatusEx.restype = wintypes.BOOL

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ok = GlobalMemoryStatusEx(ctypes.byref(mem))
        if not ok:
            raise OSError("GlobalMemoryStatusEx failed")
        return {
            "dwMemoryLoad": mem.dwMemoryLoad,
            "ullTotalPhys": mem.ullTotalPhys,
            "ullAvailPhys": mem.ullAvailPhys,
        }

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

        from app.modules.device_management.models.device_model import ONLINE

        devices = getattr(self._device_model, "devices", []) or []
        total = len(devices)

        # 判断在线逻辑：任一协议状态为 "建链成功" 则视为在线
        count_online = 0
        for d in devices:
            is_ssh_ok = d.get("ssh_connect_status") == ONLINE
            is_doip_ok = d.get("doip_connect_status") == ONLINE
            is_someip_ok = d.get("someip_connect_status") == ONLINE

            if is_ssh_ok or is_doip_ok or is_someip_ok:
                count_online += 1

        return count_online, total
