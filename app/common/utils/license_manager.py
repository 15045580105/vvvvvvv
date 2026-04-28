from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from app.common.utils.machine_code import get_machine_code
from app.common.utils.path_utils import get_app_config_path


APP_DIR = Path(get_app_config_path())
LICENSE_FILE = APP_DIR / "license.json"

STATUS_KEY: Final[str] = "激活状态:"
MACHINE_ID_KEY: Final[str] = "Machine ID:"
EXPIRE_TIME_KEY: Final[str] = "过期时间:"
REMAINING_TIME_KEY: Final[str] = "剩余时间:"
ACTIVATION_CODE_KEY: Final[str] = "Activation Code:"

MAGIC: Final[bytes] = b"ACG1"
NONCE_SIZE: Final[int] = 16
MAC_SIZE: Final[int] = 32
PAYLOAD_SIZE: Final[int] = 280
RAW_CODE_SIZE: Final[int] = len(MAGIC) + NONCE_SIZE + PAYLOAD_SIZE + MAC_SIZE
ACTIVATION_CODE_LENGTH: Final[int] = 443
DEFAULT_SECRET: Final[bytes] = b"ACG::replace-this-with-a-production-secret::2026"

MACHINE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-F0-9]{64}$")
MACHINE_FIELD_SIZE: Final[int] = 64
NAME_FIELD_SIZE: Final[int] = 48
DEPARTMENT_FIELD_SIZE: Final[int] = 48
EMAIL_FIELD_SIZE: Final[int] = 72


class ActivationCodeError(ValueError):
    pass


@dataclass(slots=True)
class LicenseUserInfo:
    name: str = ""
    department: str = ""
    email: str = ""


@dataclass(slots=True)
class DecodedLicense:
    token: str
    generate_time: datetime
    expire_time: datetime
    license_days: int
    expire_code_seconds: int
    activated_count: int
    machine_id: str
    user_info: LicenseUserInfo

    @property
    def activation_deadline(self) -> datetime:
        return self.generate_time + timedelta(seconds=self.expire_code_seconds)


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


class LicenseCodec:
    def __init__(self, secret: bytes | None = None):
        master_secret = secret or os.getenv("ACG_MASTER_SECRET", "").encode("utf-8") or DEFAULT_SECRET
        self._enc_key = hmac.new(master_secret, b"enc", hashlib.sha256).digest()
        self._mac_key = hmac.new(master_secret, b"mac", hashlib.sha256).digest()

    def decode_and_verify(self, activation_code: str) -> DecodedLicense:
        if len(activation_code) != ACTIVATION_CODE_LENGTH:
            raise ActivationCodeError(f"激活码长度不正确，应为 {ACTIVATION_CODE_LENGTH} 个字符")

        raw_code = self._decode_base64(activation_code)
        if len(raw_code) != RAW_CODE_SIZE:
            raise ActivationCodeError("激活码原始长度不正确")

        magic = raw_code[: len(MAGIC)]
        if magic != MAGIC:
            raise ActivationCodeError("激活码版本头不匹配")

        nonce = raw_code[len(MAGIC): len(MAGIC) + NONCE_SIZE]
        ciphertext = raw_code[len(MAGIC) + NONCE_SIZE: -MAC_SIZE]
        mac = raw_code[-MAC_SIZE:]
        expected_mac = hmac.new(self._mac_key, magic + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ActivationCodeError("激活码签名校验失败，内容可能被篡改")

        payload = self._xor_with_keystream(ciphertext, nonce)
        return self._unpack_payload(payload)

    def _unpack_payload(self, payload: bytes) -> DecodedLicense:
        if len(payload) != PAYLOAD_SIZE:
            raise ActivationCodeError("内部载荷长度不正确")

        token_bytes, generate_ts, expire_ts, license_days, expire_code_seconds, activated_count = struct.unpack(
            ">16sQQIII", payload[:44]
        )
        offset = 44
        machine_id, offset = self._unpack_text_field(payload, offset, MACHINE_FIELD_SIZE)
        name, offset = self._unpack_text_field(payload, offset, NAME_FIELD_SIZE)
        department, offset = self._unpack_text_field(payload, offset, DEPARTMENT_FIELD_SIZE)
        email, offset = self._unpack_text_field(payload, offset, EMAIL_FIELD_SIZE)

        return DecodedLicense(
            token=str(uuid.UUID(bytes=token_bytes)),
            generate_time=datetime.fromtimestamp(generate_ts),
            expire_time=datetime.fromtimestamp(expire_ts),
            license_days=license_days,
            expire_code_seconds=expire_code_seconds,
            activated_count=activated_count,
            machine_id=machine_id,
            user_info=LicenseUserInfo(name=name, department=department, email=email),
        )

    @staticmethod
    def _unpack_text_field(payload: bytes, offset: int, max_bytes: int) -> tuple[str, int]:
        size = payload[offset]
        offset += 1
        data = payload[offset: offset + max_bytes]
        offset += max_bytes
        return data[:size].decode("utf-8"), offset

    def _xor_with_keystream(self, payload: bytes, nonce: bytes) -> bytes:
        blocks: list[bytes] = []
        counter = 0
        generated_size = 0
        while generated_size < len(payload):
            block = hmac.new(self._enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            blocks.append(block)
            generated_size += len(block)
            counter += 1
        keystream = b"".join(blocks)[: len(payload)]
        return bytes(left ^ right for left, right in zip(payload, keystream, strict=True))

    @staticmethod
    def _decode_base64(activation_code: str) -> bytes:
        padding = "=" * ((4 - len(activation_code) % 4) % 4)
        try:
            return base64.urlsafe_b64decode(activation_code + padding)
        except Exception as exc:  # pragma: no cover - defensive path
            raise ActivationCodeError("激活码Base64解码失败") from exc


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


def _extract_stored_activation_code(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    return normalize_activation_code(str(data.get(ACTIVATION_CODE_KEY) or data.get("activation_code") or ""))


def _is_expected_license_payload(data: dict) -> bool:
    return isinstance(data, dict) and set(data.keys()) == {
        STATUS_KEY,
        MACHINE_ID_KEY,
        EXPIRE_TIME_KEY,
        REMAINING_TIME_KEY,
        ACTIVATION_CODE_KEY,
    }


def _sync_persisted_license_payload(info: LicenseInfo, data: dict) -> None:
    expected_payload = _persisted_license_payload(info)
    if _is_expected_license_payload(data) and all(data.get(key) == value for key, value in expected_payload.items()):
        return
    _save_license(expected_payload)


def is_activated() -> bool:
    return get_license_info().activated


def get_license_info() -> LicenseInfo:
    data = _load_license()
    stored_code = _extract_stored_activation_code(data)
    if not stored_code:
        return _build_empty_license_info("未找到激活文件，请先录入激活码")

    try:
        decoded = decode_activation_code(stored_code)
    except ActivationCodeError as exc:
        info = _build_empty_license_info(f"本地激活信息无效：{exc}", status_text="校验失败")
        info.activation_code = stored_code
        return info

    try:
        current_machine = normalize_machine_id(get_machine_code())
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

    if decoded.machine_id != current_machine:
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
    normalized_code = normalize_activation_code(activation_code)
    if not normalized_code:
        return ActivationResult(False, "请输入激活码")

    try:
        decoded = decode_activation_code(normalized_code)
    except ActivationCodeError as exc:
        return ActivationResult(False, str(exc))

    try:
        current_machine = normalize_machine_id(get_machine_code())
    except ActivationCodeError as exc:
        return ActivationResult(False, f"当前机器码无效：{exc}")

    if decoded.machine_id != current_machine:
        return ActivationResult(False, "激活码中的 Machine ID 与当前设备不匹配！")

    now = datetime.now().replace(microsecond=0)
    if now > decoded.activation_deadline:
        return ActivationResult(False, "激活时间已失效，请联系管理员重新申请新的激活码！")
    if now > decoded.expire_time:
        return ActivationResult(False, "该授权已过期，无法激活！")

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
