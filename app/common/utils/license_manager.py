import json
import hashlib
from pathlib import Path
from datetime import datetime

from app.common.utils.machine_code import get_machine_code


APP_DIR = Path.home() / ".oneboxforgac"
LICENSE_FILE = APP_DIR / "license.json"
_SECRET = "GAC-ONEBOX-2025"


def _ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)


def _load_license():
    if not LICENSE_FILE.exists():
        return {}
    try:
        with LICENSE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_license(payload: dict):
    _ensure_app_dir()
    with LICENSE_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def expected_activation_code(machine_code: str | None = None) -> str:
    """根据机器码生成期望的激活码，长度约 300 字符。

    这里通过多轮 SHA-256 叠加，并拼接多段摘要，构造足够长的激活码串，
    最终截断为 300 字符以内的 HEX 串。
    """
    machine_code = machine_code or get_machine_code()
    base = f"{machine_code}-{_SECRET}".encode()
    parts = []
    data = base
    for i in range(8):  # 8 轮叠加
        h = hashlib.sha256(data).hexdigest().upper()
        parts.append(h)
        data = (h + _SECRET + str(i)).encode()
    long_code = "".join(parts)  # 8 * 64 = 512 字符
    return long_code[:300]


def is_activated() -> bool:
    data = _load_license()
    stored_code = data.get("activation_code")
    stored_machine = data.get("machine_code")
    if not stored_code or not stored_machine:
        return False
    expected = expected_activation_code(stored_machine)
    return stored_code == expected


def activate(activation_code: str) -> bool:
    machine_code = get_machine_code()
    if activation_code.upper().strip() != expected_activation_code(machine_code):
        return False
    payload = {
        "machine_code": machine_code,
        "activation_code": expected_activation_code(machine_code),
        "activated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_license(payload)
    return True


def clear_license():
    if LICENSE_FILE.exists():
        try:
            LICENSE_FILE.unlink()
        except OSError:
            pass
