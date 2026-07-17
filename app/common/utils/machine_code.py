from __future__ import annotations

import hashlib
import re
import subprocess
import winreg
from functools import lru_cache


_INVALID_SERIAL_VALUES = {
    "",
    "0",
    "00000000",
    "0000000000000000",
    "DEFAULT",
    "DEFAULT STRING",
    "NONE",
    "NULL",
    "N/A",
    "NA",
    "NOT APPLICABLE",
    "NOT AVAILABLE",
    "NOT SPECIFIED",
    "OEM",
    "OEM TO BE FILLED BY O.E.M.",
    "SYSTEM SERIAL NUMBER",
    "TO BE FILLED BY O.E.M.",
    "TO BE FILLED BY O.E.M",
    "TO BE FILLED BY OEM",
    "UNKNOWN",
}

_MACHINE_CODE_VERSION = "VCC-MACHINE-CODE-V2"


def _normalize_identifier(value: str) -> str:
    value = (value or "").strip().upper()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ._-\t\r\n")


def _is_valid_identifier(value: str) -> bool:
    normalized = _normalize_identifier(value)
    if normalized in _INVALID_SERIAL_VALUES:
        return False
    if len(normalized) < 4:
        return False
    compact = re.sub(r"[^A-Z0-9]", "", normalized)
    if not compact or len(set(compact)) <= 1:
        return False
    return True


def _run_powershell(script: str) -> str:
    try:
        result = subprocess.check_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    return result.strip()


def _read_machine_guid() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return _normalize_identifier(str(value))
    except Exception:
        return ""


def _read_cim_values(class_name: str, property_name: str, *, filters: str = "") -> list[str]:
    where_clause = f" | Where-Object {{ {filters} }}" if filters else ""
    script = (
        f"Get-CimInstance -ClassName {class_name}{where_clause} "
        f"| Select-Object -ExpandProperty {property_name} -ErrorAction SilentlyContinue"
    )
    values: list[str] = []
    for line in _run_powershell(script).splitlines():
        normalized = _normalize_identifier(line)
        if _is_valid_identifier(normalized):
            values.append(normalized)
    return sorted(set(values))


@lru_cache(maxsize=1)
def _stable_machine_components() -> tuple[str, ...]:
    """返回用于生成机器码的稳定身份组件。

    不再使用 IP、当前活动网卡、MAC、主机名、系统版本等会因网络环境或配置变化而变化的字段。

    主机器码优先只绑定 Windows MachineGuid。原因是 BIOS/主板/CPU/磁盘序列号并不保证所有 PC
    都存在或始终可读；如果把它们全部拼进主机器码，任意一个字段读取失败或硬件更换都会导致
    授权失效。硬件序列号仅在 MachineGuid 不可用时作为兜底。
    """
    machine_guid = _read_machine_guid()
    if _is_valid_identifier(machine_guid):
        return (f"WINDOWS_MACHINE_GUID={machine_guid}",)

    components: list[str] = []
    hardware_sources = [
        ("BIOS_SERIAL", "Win32_BIOS", "SerialNumber", ""),
        ("BASEBOARD_SERIAL", "Win32_BaseBoard", "SerialNumber", ""),
        ("CPU_PROCESSOR_ID", "Win32_Processor", "ProcessorId", ""),
        (
            "SYSTEM_DISK_SERIAL",
            "Win32_DiskDrive",
            "SerialNumber",
            "$_.Index -eq 0 -and $_.MediaType -notmatch 'Removable'",
        ),
    ]
    for label, class_name, property_name, filters in hardware_sources:
        for value in _read_cim_values(class_name, property_name, filters=filters):
            components.append(f"{label}={value}")

    return tuple(sorted(set(components)))


def _hash_components(components: tuple[str, ...]) -> str:
    payload = "\n".join((_MACHINE_CODE_VERSION, *components)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def get_machine_code_candidates() -> tuple[str, ...]:
    """返回当前设备可接受的稳定机器码候选集合。

    当前版本只生成一个主机器码；保留候选集合接口，是为了后续如果需要兼容旧算法或新增算法，
    授权校验层无需再改协议层和界面层。
    """
    components = _stable_machine_components()
    if not components:
        return (hashlib.sha256(b"VCC_STABLE_MACHINE_CODE_FALLBACK").hexdigest().upper(),)
    return (_hash_components(components),)


def get_machine_code() -> str:
    """获取绑定本机稳定系统/硬件身份的 64 位机器码。"""
    return get_machine_code_candidates()[0]
