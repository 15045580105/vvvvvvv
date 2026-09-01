from __future__ import annotations

import hashlib
import re
import winreg
from functools import lru_cache


class MachineCodeError(RuntimeError):
    """无法从本机获取唯一且稳定的机器码身份源时抛出。"""


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


def _read_machine_guid() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return _normalize_identifier(str(value))
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _stable_machine_components() -> tuple[str, ...]:
    """返回用于生成机器码的唯一身份组件。

    设计约定：机器码只绑定 Windows MachineGuid（注册表
    HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid）。

    不再使用任何兜底规则（硬件序列号兜底、常量兜底均已移除）：
    兜底路径一旦在某次启动时被触发，会导致机器码与激活时不一致，
    使原本有效的激活码被判定为"机器不匹配"而要求重新激活，
    这违背"同一台 PC 机器码必须唯一且不变"的设计初衷。
    MachineGuid 在系统安装后保持稳定，读取失败时直接抛出异常，
    由业务层提示用户，而不是悄悄换一个机器码。
    """
    machine_guid = _read_machine_guid()
    if not _is_valid_identifier(machine_guid):
        raise MachineCodeError(
            "无法读取本机唯一身份标识（MachineGuid），无法生成稳定的机器码。"
        )
    return (f"WINDOWS_MACHINE_GUID={machine_guid}",)


def _hash_components(components: tuple[str, ...]) -> str:
    payload = "\n".join((_MACHINE_CODE_VERSION, *components)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def get_machine_code_candidates() -> tuple[str, ...]:
    """返回当前设备唯一的稳定机器码候选集合。

    当前规则只产生一个机器码，不存在多候选、不存在兜底候选；
    保留候选集合接口是为了后续新增算法时无需改动协议层和界面层。
    """
    return (_hash_components(_stable_machine_components()),)


def get_machine_code() -> str:
    """获取绑定本机稳定系统/硬件身份的 64 位机器码。"""
    return get_machine_code_candidates()[0]
