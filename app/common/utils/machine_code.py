import hashlib
import uuid
import platform
import socket
import subprocess
from functools import lru_cache


def _run_command(cmd: str) -> str:
    try:
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True)
        lines = [line.strip() for line in result.splitlines() if line.strip() and "SerialNumber" not in line]
        return "|".join(lines)
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _extended_hardware_fingerprint() -> str:
    pieces = [
        socket.gethostname(),
        platform.system(),
        platform.release(),
        platform.version(),
        platform.machine(),
        platform.processor(),
        str(uuid.getnode()),
    ]
    wmic_cmds = [
        "wmic baseboard get SerialNumber",
        "wmic bios get SerialNumber",
        "wmic cpu get ProcessorId",
        "wmic diskdrive get SerialNumber",
    ]
    for cmd in wmic_cmds:
        output = _run_command(cmd)
        if output:
            pieces.append(output)
    payload = "|".join(filter(None, pieces))
    return payload or "fallback-machine-info"


def get_machine_code():
    """获取机器唯一标识码，更长且包含更多硬件信息"""
    try:
        machine_info = _extended_hardware_fingerprint()
        machine_hash = hashlib.sha256(machine_info.encode()).hexdigest().upper()
        return machine_hash
    except Exception:
        return hashlib.sha256(b"DEFAULT_MACHINE_CODE").hexdigest().upper()
