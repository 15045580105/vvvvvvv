from __future__ import annotations

import base64
import hashlib
import secrets
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

# 无密钥版本头。生成器端和校验端必须完全一致。
MAGIC: Final[bytes] = b"ACG2"
NONCE_SIZE: Final[int] = 16
PAYLOAD_DIGEST_SIZE: Final[int] = 16
CHECKSUM_SIZE: Final[int] = 8
PAYLOAD_SIZE: Final[int] = 280
ROUND_COUNT: Final[int] = 3
RAW_CODE_SIZE: Final[int] = len(MAGIC) + NONCE_SIZE + PAYLOAD_DIGEST_SIZE + PAYLOAD_SIZE + CHECKSUM_SIZE
ACTIVATION_CODE_LENGTH: Final[int] = 432
HEADER_STRUCT: Final[str] = ">16sQQIII"
HEADER_SIZE: Final[int] = 44

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


def _sha256(data: bytes) -> bytes:
    """统一的哈希入口，生成器端也必须使用同样的 SHA-256 规则。"""
    return hashlib.sha256(data).digest()


def _rol8(value: int, shift: int) -> int:
    """8 位循环左移。"""
    shift &= 7
    return ((value << shift) | (value >> (8 - shift))) & 0xFF


def _ror8(value: int, shift: int) -> int:
    """8 位循环右移。"""
    shift &= 7
    return ((value >> shift) | (value << (8 - shift))) & 0xFF


def _pack_text_field(text: str, max_bytes: int) -> bytes:
    """文本字段固定采用：1 字节长度 + 固定长度内容区。"""
    raw = (text or "").encode("utf-8")
    if len(raw) > max_bytes:
        raise ActivationCodeError(f"文本字段过长，最大允许 {max_bytes} 字节")
    return bytes([len(raw)]) + raw.ljust(max_bytes, b"\x00")


def _unpack_text_field(payload: bytes, offset: int, max_bytes: int) -> tuple[str, int]:
    size = payload[offset]
    offset += 1
    data = payload[offset: offset + max_bytes]
    offset += max_bytes
    return data[:size].decode("utf-8"), offset


def _pack_payload(
    *,
    token: str,
    generate_time: datetime,
    expire_time: datetime,
    license_days: int,
    expire_code_seconds: int,
    activated_count: int,
    machine_id: str,
    name: str,
    department: str,
    email: str,
) -> bytes:
    """业务字段打包成固定 280 字节 payload。"""
    header = struct.pack(
        HEADER_STRUCT,
        uuid.UUID(token).bytes,
        int(generate_time.timestamp()),
        int(expire_time.timestamp()),
        license_days,
        expire_code_seconds,
        activated_count,
    )
    payload = (
        header
        + _pack_text_field(machine_id, MACHINE_FIELD_SIZE)
        + _pack_text_field(name, NAME_FIELD_SIZE)
        + _pack_text_field(department, DEPARTMENT_FIELD_SIZE)
        + _pack_text_field(email, EMAIL_FIELD_SIZE)
    )
    if len(payload) != PAYLOAD_SIZE:
        raise ActivationCodeError(f"内部载荷长度不正确，期望 {PAYLOAD_SIZE}，实际 {len(payload)}")
    return payload


def _payload_digest(payload: bytes) -> bytes:
    """payload 摘要是无密钥方案里的公开 seed 组成部分。"""
    return _sha256(payload)[:PAYLOAD_DIGEST_SIZE]


def _build_seed(nonce: bytes, payload_digest: bytes) -> bytes:
    """seed 仅依赖激活码自身内容，不依赖当前 PC、密钥或环境变量。"""
    return _sha256(MAGIC + nonce + payload_digest)


def _calc_checksum(nonce: bytes, payload_digest: bytes, obfuscated_payload: bytes) -> bytes:
    """完整性校验：用于发现复制错误、截断或格式损坏。"""
    return _sha256(MAGIC + nonce + payload_digest + obfuscated_payload)[:CHECKSUM_SIZE]


def _make_keystream(seed: bytes, round_index: int, size: int) -> bytes:
    """每轮都根据 seed + round + counter 生成伪随机字节流。"""
    blocks: list[bytes] = []
    current_len = 0
    counter = 0
    while current_len < size:
        block = _sha256(seed + round_index.to_bytes(1, "big") + counter.to_bytes(4, "big"))
        blocks.append(block)
        current_len += len(block)
        counter += 1
    return b"".join(blocks)[:size]


def _byte_offset(seed: bytes, round_index: int, index: int) -> int:
    """每个字节都使用与位置相关的偏移量，避免固定常量 XOR 过于单薄。"""
    return (seed[(index + round_index * 5) % len(seed)] + index * 11 + round_index * 17) & 0xFF


def _bit_shift(seed: bytes, round_index: int, index: int) -> int:
    """位移量始终在 1~8 之间。"""
    return ((seed[(index * 3 + round_index) % len(seed)] + index + round_index) & 0x07) + 1


def _make_permutation(seed: bytes, size: int) -> list[int]:
    """根据 seed 生成字节置换表；生成器端和校验端必须保持一致。"""
    order = list(range(size))
    state = seed
    for i in range(size - 1, 0, -1):
        state = _sha256(state + i.to_bytes(2, "big"))
        j = int.from_bytes(state[:4], "big") % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def _permute(data: bytes, permutation: list[int]) -> bytes:
    return bytes(data[idx] for idx in permutation)


def _unpermute(data: bytes, permutation: list[int]) -> bytes:
    restored = bytearray(len(data))
    for out_index, src_index in enumerate(permutation):
        restored[src_index] = data[out_index]
    return bytes(restored)


def _encode_round(data: bytes, seed: bytes, round_index: int) -> bytes:
    """单轮混淆规则：加偏移 -> 循环左移 -> XOR 字节流。"""
    stream = _make_keystream(seed, round_index, len(data))
    out = bytearray(len(data))
    for i, value in enumerate(data):
        value = (value + _byte_offset(seed, round_index, i)) & 0xFF
        value = _rol8(value, _bit_shift(seed, round_index, i))
        value ^= stream[i]
        out[i] = value
    return bytes(out)


def _decode_round(data: bytes, seed: bytes, round_index: int) -> bytes:
    """单轮反混淆规则：XOR -> 循环右移 -> 减偏移。"""
    stream = _make_keystream(seed, round_index, len(data))
    out = bytearray(len(data))
    for i, value in enumerate(data):
        value ^= stream[i]
        value = _ror8(value, _bit_shift(seed, round_index, i))
        value = (value - _byte_offset(seed, round_index, i)) & 0xFF
        out[i] = value
    return bytes(out)


class LicenseCodec:
    """无密钥编解码器。

    规则由 MAGIC、payload 打包方式、seed 规则、字节置换、多轮混淆、checksum
    和 Base64URL 编码共同决定。生成器端必须逐项保持一致，才能稳定互通。

    这个类只负责“激活码字符串 <-> 结构化授权信息”的转换，不处理：
    - 本地 license.json 读写
    - 当前机器码获取
    - 是否允许激活/是否已过期等业务判断
    这些都由 license_manager.py 负责。
    """

    def generate(
        self,
        *,
        token: str,
        generate_time: datetime,
        expire_time: datetime,
        license_days: int,
        expire_code_seconds: int,
        activated_count: int,
        machine_id: str,
        name: str,
        department: str,
        email: str,
    ) -> str:
        """提供给生成器端复用的编码入口。

        编码流程固定为：
        1. 先把业务字段打包成固定 280 字节 payload
        2. 计算 payload_digest，用来参与 seed 生成
        3. 生成 nonce，使同样的业务参数每次编码结果也不完全相同
        4. 根据 seed 先做字节置换，再做多轮混淆
        5. 计算 checksum，用于校验内容是否损坏
        6. 拼接 raw_code，最后用 Base64URL 输出成字符串
        """
        payload = _pack_payload(
            token=token,
            generate_time=generate_time,
            expire_time=expire_time,
            license_days=license_days,
            expire_code_seconds=expire_code_seconds,
            activated_count=activated_count,
            machine_id=machine_id,
            name=name,
            department=department,
            email=email,
        )
        nonce = secrets.token_bytes(NONCE_SIZE)
        digest = _payload_digest(payload)
        seed = _build_seed(nonce, digest)
        permutation = _make_permutation(seed, len(payload))

        # 先置换，再做多轮混淆。这样结构特征更不明显。
        obfuscated = _permute(payload, permutation)
        for round_index in range(ROUND_COUNT):
            obfuscated = _encode_round(obfuscated, seed, round_index)

        checksum = _calc_checksum(nonce, digest, obfuscated)
        raw_code = MAGIC + nonce + digest + obfuscated + checksum
        return base64.urlsafe_b64encode(raw_code).decode("ascii").rstrip("=")

    def decode_and_verify(self, activation_code: str) -> DecodedLicense:
        """校验并解码激活码。

        这是程序端校验链路里最核心的一步，只负责“结构正确且内容可还原”，
        不负责机器码匹配、激活时效、授权过期等业务规则。

        解码流程固定为：
        1. 校验激活码长度
        2. Base64URL 解码 raw_code
        3. 校验版本头 MAGIC
        4. 取出 nonce / digest / obfuscated / checksum
        5. 先校验 checksum，发现复制错误或内容损坏时立即失败
        6. 依据 nonce + digest 重新生成 seed
        7. 按相反顺序执行多轮反混淆
        8. 逆置换恢复原始 payload
        9. 重新计算 payload_digest，确认还原结果一致
        10. 将 payload 解包为 DecodedLicense
        """
        if len(activation_code) != ACTIVATION_CODE_LENGTH:
            raise ActivationCodeError(f"激活码长度不正确，应为 {ACTIVATION_CODE_LENGTH} 个字符")

        raw_code = self._decode_base64(activation_code)
        if len(raw_code) != RAW_CODE_SIZE:
            raise ActivationCodeError("激活码原始长度不正确")

        offset = 0
        magic = raw_code[offset: offset + len(MAGIC)]
        offset += len(MAGIC)
        if magic != MAGIC:
            raise ActivationCodeError("激活码版本头不匹配")

        nonce = raw_code[offset: offset + NONCE_SIZE]
        offset += NONCE_SIZE
        digest = raw_code[offset: offset + PAYLOAD_DIGEST_SIZE]
        offset += PAYLOAD_DIGEST_SIZE
        obfuscated = raw_code[offset: offset + PAYLOAD_SIZE]
        offset += PAYLOAD_SIZE
        checksum = raw_code[offset: offset + CHECKSUM_SIZE]

        # 第一步完整性校验：优先发现激活码是否被截断、改动或复制损坏。
        expected_checksum = _calc_checksum(nonce, digest, obfuscated)
        if checksum != expected_checksum:
            raise ActivationCodeError("激活码完整性校验失败，内容已损坏或格式无效")

        # 第二步内容恢复：按“编码的逆过程”恢复 payload。
        seed = _build_seed(nonce, digest)
        payload = obfuscated
        for round_index in reversed(range(ROUND_COUNT)):
            payload = _decode_round(payload, seed, round_index)

        permutation = _make_permutation(seed, len(payload))
        payload = _unpermute(payload, permutation)

        # 第三步结果一致性校验：防止虽然能解出字节，但内容并非原始 payload。
        if _payload_digest(payload) != digest:
            raise ActivationCodeError("激活码内容恢复失败，数据不一致")

        return self._unpack_payload(payload)

    def _unpack_payload(self, payload: bytes) -> DecodedLicense:
        if len(payload) != PAYLOAD_SIZE:
            raise ActivationCodeError("内部载荷长度不正确")

        token_bytes, generate_ts, expire_ts, license_days, expire_code_seconds, activated_count = struct.unpack(
            HEADER_STRUCT, payload[:HEADER_SIZE]
        )
        offset = HEADER_SIZE
        machine_id, offset = _unpack_text_field(payload, offset, MACHINE_FIELD_SIZE)
        name, offset = _unpack_text_field(payload, offset, NAME_FIELD_SIZE)
        department, offset = _unpack_text_field(payload, offset, DEPARTMENT_FIELD_SIZE)
        email, offset = _unpack_text_field(payload, offset, EMAIL_FIELD_SIZE)

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
    def _decode_base64(activation_code: str) -> bytes:
        # Base64URL 解码时补齐 '='，规则必须与生成器端一致。
        padding = "=" * ((4 - len(activation_code) % 4) % 4)
        try:
            return base64.urlsafe_b64decode(activation_code + padding)
        except Exception as exc:  # pragma: no cover - defensive path
            raise ActivationCodeError("激活码Base64解码失败") from exc

