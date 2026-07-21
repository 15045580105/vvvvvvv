from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from app.common.utils.license_codec_core import (
    ActivationCodeError,
    DecodedLicense,
    LicenseCodec,
)
from app.common.utils.crypto_utils import dpt_encryptor
from app.common.utils.machine_code import get_machine_code_candidates
from app.common.utils.path_utils import get_app_config_path


APP_DIR = Path(get_app_config_path())
LICENSE_FILE = APP_DIR / "license.json"

# license.json 不再直接保存明文授权字段，而是保存如下包装结构：
# {
#   "encrypted": true,
#   "version": 1,
#   "payload": "...Fernet加密后的授权JSON..."
# }
# Fernet 自带完整性校验，用户手动篡改 payload 后会导致解密失败，从而无法绕过过期时间校验。
LICENSE_ENCRYPTED_FLAG: Final[str] = "encrypted"
LICENSE_ENCRYPTED_VERSION_KEY: Final[str] = "version"
LICENSE_ENCRYPTED_PAYLOAD_KEY: Final[str] = "payload"
LICENSE_ENCRYPTED_VERSION: Final[int] = 1
# 仅在内存中使用：标记本次读取来源是旧明文文件，后续同步时必须重写为加密格式。
LICENSE_LEGACY_PLAINTEXT_MARKER: Final[str] = "__legacy_plaintext_license__"

STATUS_KEY: Final[str] = "激活状态:"
MACHINE_ID_KEY: Final[str] = "Machine ID:"
EXPIRE_TIME_KEY: Final[str] = "过期时间:"
REMAINING_TIME_KEY: Final[str] = "剩余时间:"
ACTIVATION_CODE_KEY: Final[str] = "Activation Code:"

# 机器码校验仍然放在业务层：这属于本地设备环境规则，不属于纯编解码核心。
MACHINE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-F0-9]{64}$")


@dataclass(slots=True)
class LicenseInfo:
    activated: bool
    status_text: str
    message: str
    machine_id: str = ""
    activation_code: str = ""
    token: str = ""
    generate_time_text: str = "--"
    activated_at_text: str = "--"
    expire_time_text: str = "--"
    activation_deadline_text: str = "--"
    remaining_days: int = 0
    remaining_seconds: int = 0
    license_days: int = 0
    expire_code_seconds: int = 0
    activated_count: int = 0
    user_name: str = ""
    department: str = ""
    email: str = ""


@dataclass(slots=True)
class ActivationResult:
    success: bool
    message: str
    license_info: LicenseInfo | None = None


def _ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)


def _decrypt_license_payload(encrypted_payload: str) -> dict:
    """解密 license.json 中保存的加密载荷，并还原为授权信息字典。

    注意：这里仅负责“文件存储层”的解密；激活码合法性、机器码匹配、是否过期等
    业务校验仍由 get_license_info()/activate() 执行，避免把存储加密和授权规则混在一起。
    """
    if not encrypted_payload:
        return {}
    try:
        decrypted_text = dpt_encryptor.decrypt(encrypted_payload.encode("utf-8"))
        decrypted_data = json.loads(decrypted_text)
        return decrypted_data if isinstance(decrypted_data, dict) else {}
    except Exception:
        # Fernet 解密失败通常表示文件被篡改、密钥不匹配或内容损坏；此时按无有效授权处理。
        return {}


def _encrypt_license_payload(payload: dict) -> str:
    """把授权信息字典序列化后加密，返回可写入 JSON 文件的文本密文。"""
    # separators 去掉不必要空格，减少明文长度；ensure_ascii=False 保留中文字段名。
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return dpt_encryptor.encrypt(plaintext).decode("utf-8")


def _load_license() -> dict:
    if not LICENSE_FILE.exists():
        return {}
    try:
        raw_text = LICENSE_FILE.read_text(encoding="utf-8").strip()
        if not raw_text:
            return {}

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # 兼容“整个文件直接保存为 Fernet token”的加密形式，便于以后格式调整。
            return _decrypt_license_payload(raw_text)

        if not isinstance(data, dict):
            return {}

        if data.get(LICENSE_ENCRYPTED_FLAG) is True:
            # 新格式：license.json 只暴露加密包装信息，真实授权字段必须解密后才能获取。
            return _decrypt_license_payload(str(data.get(LICENSE_ENCRYPTED_PAYLOAD_KEY) or ""))

        # 兼容旧版本明文 license.json：打上内存标记，确保首次读取后会触发同步并重新加密保存。
        data[LICENSE_LEGACY_PLAINTEXT_MARKER] = True
        return data
    except Exception:
        return {}


def _save_license(payload: dict):
    _ensure_app_dir()
    encrypted_data = {
        LICENSE_ENCRYPTED_FLAG: True,
        LICENSE_ENCRYPTED_VERSION_KEY: LICENSE_ENCRYPTED_VERSION,
        LICENSE_ENCRYPTED_PAYLOAD_KEY: _encrypt_license_payload(payload),
    }
    with LICENSE_FILE.open("w", encoding="utf-8") as f:
        # 文件仍保持 JSON 结构，便于排查“是否为加密格式”；授权明细字段不再明文落盘。
        json.dump(encrypted_data, f, ensure_ascii=False, indent=2)


def normalize_machine_id(machine_id: str) -> str:
    value = (machine_id or "").strip().upper()
    if not value:
        raise ActivationCodeError("机器码为空")
    if not MACHINE_ID_PATTERN.fullmatch(value):
        raise ActivationCodeError("机器码必须是 64 位大写十六进制字符串")
    return value


def normalize_activation_code(activation_code: str) -> str:
    return "".join((activation_code or "").split())


def decode_activation_code(activation_code: str) -> DecodedLicense:
    """程序端统一的激活码解析入口。

    这里只做两件事：
    1. 清理用户输入中的空白字符
    2. 调用 LicenseCodec 完成底层校验和解码

    任何“机器码是否一致”“是否允许激活”“是否过期”等业务判断，
    都不在这里处理，而是在 get_license_info()/activate() 中继续判断。
    """
    normalized_code = normalize_activation_code(activation_code)
    return LicenseCodec().decode_and_verify(normalized_code)


def _format_datetime(value: datetime | None) -> str:
    if not value:
        return "--"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _build_license_info(
    decoded: DecodedLicense,
    activation_code: str,
    *,
    activated: bool,
    status_text: str,
    message: str,
) -> LicenseInfo:
    now = datetime.now().replace(microsecond=0)
    remaining_seconds = max(0, int((decoded.expire_time - now).total_seconds()))
    remaining_days = (remaining_seconds + 86399) // 86400 if remaining_seconds > 0 else 0
    return LicenseInfo(
        activated=activated,
        status_text=status_text,
        message=message,
        machine_id=decoded.machine_id,
        activation_code=activation_code,
        token=decoded.token,
        generate_time_text=_format_datetime(decoded.generate_time),
        expire_time_text=_format_datetime(decoded.expire_time),
        activation_deadline_text=_format_datetime(decoded.activation_deadline),
        remaining_days=remaining_days,
        remaining_seconds=remaining_seconds,
        license_days=decoded.license_days,
        expire_code_seconds=decoded.expire_code_seconds,
        activated_count=decoded.activated_count,
        user_name=decoded.user_info.name,
        department=decoded.user_info.department,
        email=decoded.user_info.email,
    )


def _build_empty_license_info(message: str, *, status_text: str = "未激活") -> LicenseInfo:
    return LicenseInfo(activated=False, status_text=status_text, message=message)


def _format_remaining_time_text(remaining_days: int) -> str:
    return f"{remaining_days}天"


def _persisted_license_payload(info: LicenseInfo) -> dict:
    return {
        STATUS_KEY: info.status_text or "--",
        MACHINE_ID_KEY: info.machine_id or "--",
        EXPIRE_TIME_KEY: info.expire_time_text or "--",
        REMAINING_TIME_KEY: _format_remaining_time_text(info.remaining_days),
        ACTIVATION_CODE_KEY: info.activation_code or "",
    }


def _extract_stored_activation_code(data: object) -> str:
    if isinstance(data, dict):
        return normalize_activation_code(str(data.get(ACTIVATION_CODE_KEY) or data.get("activation_code") or ""))
    return ""


def _is_expected_license_payload(data: object) -> bool:
    return isinstance(data, dict) and set(data.keys()) == {
        STATUS_KEY,
        MACHINE_ID_KEY,
        EXPIRE_TIME_KEY,
        REMAINING_TIME_KEY,
        ACTIVATION_CODE_KEY,
    }


def _is_legacy_plaintext_payload(data: object) -> bool:
    """判断本次读取是否来自旧版明文 license.json，用于触发加密迁移。"""
    return isinstance(data, dict) and data.get(LICENSE_LEGACY_PLAINTEXT_MARKER) is True


def _sync_persisted_license_payload(info: LicenseInfo, data: object) -> None:
    expected_payload = _persisted_license_payload(info)
    if isinstance(data, dict) and _is_expected_license_payload(data) and not _is_legacy_plaintext_payload(data):
        if all(data.get(key) == value for key, value in expected_payload.items()):
            return
    _save_license(expected_payload)


def is_activated() -> bool:
    return get_license_info().activated


def get_license_info() -> LicenseInfo:
    """读取当前本地授权信息，并给界面提供可直接展示的结果。

    校验链路如下：
    1. 从 license.json 中读取保存的激活码
    2. 调用 decode_activation_code 做底层格式/内容校验
    3. 获取当前机器码，并与激活码中的 machine_id 比较
    4. 判断授权是否已经过期
    5. 把解码结果整理成界面需要展示的 LicenseInfo

    这个函数用于“查看当前授权状态”，不会写入新的激活码，
    但在状态发生变化时会同步修正本地展示字段。
    """
    data = _load_license()
    stored_code = _extract_stored_activation_code(data)
    if not stored_code:
        if _is_legacy_plaintext_payload(data):
            # 旧明文文件即使没有激活码，也重写为加密空授权，避免继续暴露 license.json 明文字段。
            _save_license(_persisted_license_payload(_build_empty_license_info("未找到激活文件，请先录入激活码")))
        return _build_empty_license_info("未找到激活文件，请先录入激活码")

    try:
        # 第一步：先确认激活码本身结构正确，且能成功还原出授权内容。
        decoded = decode_activation_code(stored_code)
    except ActivationCodeError as exc:
        info = _build_empty_license_info(f"本地激活信息无效：{exc}", status_text="校验失败")
        info.activation_code = stored_code
        if _is_legacy_plaintext_payload(data):
            # 激活码无效时也要迁移为加密格式，避免用户从明文文件继续修改授权字段。
            _save_license(_persisted_license_payload(info))
        return info

    try:
        # 第二步：获取当前设备稳定机器码候选集合，并校验格式是否正常。
        current_machines = {normalize_machine_id(machine_code) for machine_code in get_machine_code_candidates()}
    except ActivationCodeError as exc:
        info = _build_license_info(
            decoded,
            stored_code,
            activated=False,
            status_text="机器码异常",
            message=f"当前机器码无效：{exc}",
        )
        _sync_persisted_license_payload(info, data)
        return info

    # 第三步：机器码匹配校验。激活码只能在生成时指定的设备上使用。
    if decoded.machine_id not in current_machines:
        info = _build_license_info(
            decoded,
            stored_code,
            activated=False,
            status_text="机器不匹配",
            message="激活码中的 Machine ID 与当前设备不一致",
        )
        _sync_persisted_license_payload(info, data)
        return info

    now = datetime.now().replace(microsecond=0)
    # 第四步：授权有效期校验。到期后即使激活码内容合法，也视为无效授权。
    if now > decoded.expire_time:
        info = _build_license_info(
            decoded,
            stored_code,
            activated=False,
            status_text="已过期",
            message="当前授权已过期，请重新申请激活码",
        )
        _sync_persisted_license_payload(info, data)
        return info

    info = _build_license_info(
        decoded,
        stored_code,
        activated=True,
        status_text="已激活",
        message="授权有效",
    )
    _sync_persisted_license_payload(info, data)
    return info


def activate(activation_code: str) -> ActivationResult:
    """用户手动录入激活码时的业务入口。

    激活流程如下：
    1. 清理输入内容
    2. 调用 decode_activation_code 做底层解码
    3. 校验当前机器码是否与授权绑定一致
    4. 校验“激活时限”是否已经失效
    5. 校验授权是否已经过期
    6. 将授权信息以精简展示字段写入本地 license.json
    """
    normalized_code = normalize_activation_code(activation_code)
    if not normalized_code:
        return ActivationResult(False, "请输入激活码")

    try:
        # 第一步：校验激活码本身是否合法且可解码。
        decoded = decode_activation_code(normalized_code)
    except ActivationCodeError as exc:
        return ActivationResult(False, str(exc))

    try:
        # 第二步：检查当前设备稳定机器码候选集合是否合法。
        current_machines = {normalize_machine_id(machine_code) for machine_code in get_machine_code_candidates()}
    except ActivationCodeError as exc:
        return ActivationResult(False, f"当前机器码无效：{exc}")

    # 第三步：机器码绑定校验。
    if decoded.machine_id not in current_machines:
        return ActivationResult(False, "激活码中的 Machine ID 与当前设备不匹配！")

    now = datetime.now().replace(microsecond=0)
    # 第四步：激活码本身存在“必须在某时限内完成激活”的限制。
    if now > decoded.activation_deadline:
        return ActivationResult(False, "激活时间已失效，请联系管理员重新申请新的激活码！")
    # 第五步：授权有效期检查。
    if now > decoded.expire_time:
        return ActivationResult(False, "该授权已过期，无法激活！")

    # 第六步：校验通过后，仅把界面展示需要的信息写入本地，避免暴露更多内部字段。
    _save_license(
        _persisted_license_payload(
            _build_license_info(
                decoded,
                normalized_code,
                activated=True,
                status_text="已激活",
                message="授权有效",
            )
        )
    )
    return ActivationResult(True, "激活成功", get_license_info())


def clear_license():
    if LICENSE_FILE.exists():
        try:
            LICENSE_FILE.unlink()
        except OSError:
            pass
