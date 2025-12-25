from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Dict, Any, Union
import struct


# -----------------------------
# 数据结构
# -----------------------------


@dataclass
class DPTFieldDef:
    """单个信号/字段在 DPT 文件中的定义。"""
    name: str  # 对应 JSON 中的 description
    byte_offset: int
    byte_length: int
    encoding: str = "Unsigned"
    conversion: Any = None
    bit_fields: Dict[str, Any] = field(default_factory=dict)
    fixed_value: Any = None

    # 内部使用
    key: str = "" # JSON key


@dataclass
class DPTFieldValue:
    """解析后的单个字段结果。"""
    name: str
    range_str: str # Bit / Byte range string
    raw_hex: str   # Raw value in Hex or Binary
    parsed_value: str # Parsed/Converted value
    status: str = "" # Additional status info


@dataclass
class DPTParseResult:
    """一次解析的整体结果。"""
    bytes_hex: str
    fields: List[DPTFieldValue] = field(default_factory=list)
    description: str = "" # DID description from DPT file

    def to_table_rows(self) -> List[List[str]]:
        """转换为表格行。

        列定义:
        - Byte / Bit
        - Function / Name
        - Value (Raw/Hex/Bin)
        - Status / Unit (Parsed Value)
        """
        rows: List[List[str]] = []
        for f in self.fields:
            rows.append([
                f.range_str,
                f.name,
                f.raw_hex,
                f.parsed_value,
            ])
        return rows


# -----------------------------
# DPT 解析主入口
# -----------------------------


class DPTParser:
    def __init__(self, field_defs: List[DPTFieldDef], description: str = ""):
        # 按 byte_offset 排序
        self._fields = sorted(field_defs, key=lambda f: f.byte_offset)
        self.description = description

    @classmethod
    def from_dict_config(cls, config: Dict[str, Any]) -> "DPTParser":
        """从 dict 配置构造解析器。

        支持两种格式：
        1. {"fields": [...]} (旧格式)
        2. {"field_key": {...}, ...} (新格式)
        """
        fields: List[DPTFieldDef] = []

        # 检查是否是旧格式
        if "fields" in config and isinstance(config["fields"], list):
            # 旧格式转换逻辑 (略，或者假设不再使用旧格式，或者做简单兼容)
            # 这里为了支持新需求，主要处理新格式
            pass

        # 处理新格式：遍历字典
        # 如果 config 包含 "fields" 键且是列表，则遍历该列表（兼容旧代码逻辑，如果需要）
        # 但根据 dpt_service.py 的修改，传入的 config 可能是 {"hardware_code": {...}}

        source = config
        if "fields" in config and isinstance(config["fields"], list):
             # 如果是旧格式列表，暂不支持或需要适配，这里假设传入的是新格式字典
             # 或者如果 dpt_service 传递了 {"fields": list}，我们需要处理
             source = {f["name"]: f for f in config["fields"]} # 尝试转换

        for key, item in source.items():
            if not isinstance(item, dict):
                continue

            fields.append(
                DPTFieldDef(
                    key=key,
                    name=item.get("description", key),
                    byte_offset=int(item.get("byte_offset", 0)),
                    byte_length=int(item.get("byte_length", 0)),
                    encoding=item.get("encoding", "Unsigned"),
                    conversion=item.get("conversion"),
                    bit_fields=item.get("bit_fields", {}),
                    fixed_value=item.get("fixed_value")
                )
            )
        return cls(fields)

    def parse_bytes(self, data: Union[bytes, bytearray, Iterable[int]]) -> DPTParseResult:
        if isinstance(data, (bytearray, list, tuple)):
            data_bytes = bytes(data)
        elif isinstance(data, bytes):
            data_bytes = data
        else:
            data_bytes = bytes(int(x) & 0xFF for x in data)

        bytes_hex = " ".join(f"{b:02X}" for b in data_bytes)
        result = DPTParseResult(bytes_hex=bytes_hex, description=self.description)

        for fdef in self._fields:
            # 提取字节
            start = fdef.byte_offset
            end = start + fdef.byte_length
            if start >= len(data_bytes):
                continue

            chunk = data_bytes[start:min(end, len(data_bytes))]

            # 如果有 bit_fields，则解析位
            if fdef.bit_fields:
                self._parse_bit_fields(fdef, chunk, result)
            else:
                self._parse_standard_field(fdef, chunk, result)

        return result

    def _parse_standard_field(self, fdef: DPTFieldDef, chunk: bytes, result: DPTParseResult):
        # Range string
        if fdef.byte_length == 1:
            range_str = f"{fdef.byte_offset}/ALL"
        else:
            range_str = f"{fdef.byte_offset}-{fdef.byte_offset + fdef.byte_length - 1}/ALL"

        # Raw Hex
        raw_hex = chunk.hex(' ').upper()

        # Parsed Value
        parsed_val = ""

        if fdef.encoding == "ASCII":
            try:
                parsed_val = chunk.decode("ascii")
            except:
                parsed_val = chunk.decode("ascii", errors="replace")
        elif fdef.encoding == "Unsigned":
            # Big-endian integer
            val = int.from_bytes(chunk, byteorder='big', signed=False)

            # Conversion
            if fdef.conversion:
                if isinstance(fdef.conversion, dict):
                    # Try exact match
                    # JSON keys are strings, convert val to string
                    val_str = str(val)
                    # Check if conversion has keys like "0", "1"
                    # Also check for range mapping if needed (not implemented yet based on simple dict)
                    # dpt.json example: "conversion": {"0": "Link up", ...}
                    if val_str in fdef.conversion:
                        parsed_val = fdef.conversion[val_str]
                    else:
                        parsed_val = str(val)
                elif isinstance(fdef.conversion, str):
                    parsed_val = f"{val} ({fdef.conversion})"
                else:
                    parsed_val = str(val)
            else:
                parsed_val = str(val)
        else:
            parsed_val = raw_hex

        result.fields.append(DPTFieldValue(
            name=fdef.name,
            range_str=range_str,
            raw_hex=raw_hex,
            parsed_value=parsed_val
        ))

    def _parse_bit_fields(self, fdef: DPTFieldDef, chunk: bytes, result: DPTParseResult):
        # Convert chunk to bits string
        # Assuming big-endian for bits within bytes?
        # Usually bit 0 is LSB or MSB depending on definition.
        # dpt.json example: "bit_0": "Link up".
        # Usually bit 0 is the Least Significant Bit (LSB).

        val = int.from_bytes(chunk, byteorder='big', signed=False)

        # Sort bit fields by bit index
        # Keys are "bit_0", "bit_1", etc.
        # Need to parse "bit_X" or "bit_X_Y" (range)?
        # dpt.json has "bit_0", "bit_1".

        sorted_bits = []
        for k, v in fdef.bit_fields.items():
            if k.startswith("bit_"):
                try:
                    idx = int(k.split("_")[1])
                    sorted_bits.append((idx, v))
                except:
                    pass

        sorted_bits.sort(key=lambda x: x[0])

        for bit_idx, bit_def in sorted_bits:
            # Extract bit value
            # Assuming bit_0 is LSB (value & 1)
            bit_val = (val >> bit_idx) & 1

            # Calculate absolute byte index and relative bit index if needed
            # But user requested "ByteIndex/BitIndex"
            # If the field spans multiple bytes, we need to know which byte this bit belongs to.
            # Assuming bit_0 is LSB of the whole chunk (Big Endian integer).
            # If chunk is 1 byte: bit 0 is LSB.
            # If chunk is 2 bytes: bit 0 is LSB of byte 1 (the last byte).
            # Wait, usually "bit 0" in these definitions refers to the bit within the byte if it's a byte-based definition.
            # But here we read `byte_length` bytes.
            # If `byte_length` is 1, then `byte_offset` is the byte index.
            # `bit_idx` is the bit index.

            # If `byte_length` > 1, it gets complicated.
            # Assuming byte_length=1 for bit_fields usually.

            current_byte_offset = fdef.byte_offset
            # If multiple bytes, we might need to adjust current_byte_offset based on bit_idx
            # But let's assume simple case first or that bit_idx is within the chunk.

            range_str = f"{current_byte_offset}/{bit_idx}"

            raw_hex = str(bit_val)

            parsed_val = str(bit_val)
            conversion = bit_def.get("conversion")
            if conversion and isinstance(conversion, dict):
                val_str = str(bit_val)
                if val_str in conversion:
                    parsed_val = conversion[val_str]

            description = bit_def.get("description", "")

            result.fields.append(DPTFieldValue(
                name=description,
                range_str=range_str,
                raw_hex=raw_hex,
                parsed_value=parsed_val
            ))


def parse_bytes_to_table_rows(
    data: Union[bytes, bytearray, Iterable[int]],
    field_defs: Iterable[DPTFieldDef],
) -> List[List[str]]:
    parser = DPTParser(list(field_defs))
    result = parser.parse_bytes(data)
    return result.to_table_rows()


