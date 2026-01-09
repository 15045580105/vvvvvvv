from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Dict, Any, Union


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
    encoding: str = "" # Encoding format
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
        1. {"fields": [...]} (列表格式)
        2. {"field_key": {...}, ...} (字典格式)
        """
        fields: List[DPTFieldDef] = []

        if "fields" in config and isinstance(config["fields"], list):
            # List format
            for i, item in enumerate(config["fields"]):
                if not isinstance(item, dict): continue
                
                # Use description as name if available, else use index or key
                name = item.get("description", item.get("name", f"Field_{i}"))
                
                fields.append(
                    DPTFieldDef(
                        key=str(i),
                        name=name,
                        byte_offset=int(item.get("byte_offset", 0)),
                        byte_length=int(item.get("byte_length", 0)),
                        encoding=item.get("encoding", "Unsigned"),
                        conversion=item.get("conversion"),
                        bit_fields=item.get("bit_fields", {}),
                        fixed_value=item.get("fixed_value")
                    )
                )
        else:
            # Dict format
            for key, item in config.items():
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

        # Raw Hex (Value Column): Always space separated hex strings
        raw_hex = chunk.hex(' ').upper()

        # Parsed Value (Status/Unit Column)
        parsed_val = ""

        # Normalize Encoding
        enc = str(fdef.encoding).strip().upper() if fdef.encoding else "UNSIGNED"
        conv = fdef.conversion

        # --- 1. ASCII Processing ---
        # Explicit ASCII encoding takes precedence. User specified that Encoding contains ASCII info.
        is_ascii = "ASCII" in enc or "STRING" in enc or "CHAR" in enc

        if is_ascii:
            try:
                # Decode bytes to ASCII string
                # 'ignore' to skip non-printable bytes without showing errors
                decoded = chunk.decode("ascii", errors="ignore")
                # Filter null bytes which are common in fixed-length strings
                parsed_val = decoded.replace('\x00', '')
            except:
                parsed_val = raw_hex

        # --- 2. Numeric / Map Processing ---
        else:
            # Determine numeric value
            is_signed = "SIGNED" in enc or "INTEGER" in enc
            if is_signed:
                val = int.from_bytes(chunk, byteorder='big', signed=True)
            else:
                val = int.from_bytes(chunk, byteorder='big', signed=False)

            # Apply Conversion logic
            if conv:
                if isinstance(conv, dict):
                    if conv.get("type") == "linear":
                        # Linear: y = x * Resolution + Offset
                        res = float(conv.get("resolution", 1.0))
                        off = float(conv.get("offset", 0.0))
                        phy_val = val * res + off
                        if phy_val.is_integer():
                            parsed_val = str(int(phy_val))
                        else:
                            parsed_val = f"{phy_val:.6f}".rstrip('0').rstrip('.')
                    else:
                        # Enum / Map
                        # Try exact match for stringified integer
                        val_str = str(val)
                        if val_str in conv:
                            parsed_val = conv[val_str]
                        else:
                            # If not found in map, show original value
                            # If it's a long field, fallback to hex to avoid giant integers
                            if fdef.byte_length > 8:
                                parsed_val = raw_hex
                            else:
                                parsed_val = str(val)

                elif isinstance(conv, str):
                    # Simple String = Unit
                    if conv.upper() != "NONE":
                        # If long field and just a unit string, displaying huge int + unit is weird.
                        # Maybe still show Hex? Or trust the user wanted a unit.
                        # Usually long fields with units are rare.
                        if fdef.byte_length > 8:
                             parsed_val = f"{raw_hex} ({conv})"
                        else:
                             parsed_val = f"{val} {conv}"
                    else:
                        # Conversion is "None" string?
                         if fdef.byte_length > 8:
                            parsed_val = raw_hex
                         else:
                            parsed_val = str(val)
            else:
                # No conversion
                if "HEX" in enc:
                    parsed_val = raw_hex
                else:
                    # If byte length > 8 and no conversion, giant integers are usually wrongly encoded strings or hex
                    # Fallback to Hex if it looks like a large raw dump
                    if fdef.byte_length > 8:
                        parsed_val = raw_hex
                    else:
                        parsed_val = str(val)

        # Final Fallback
        if not parsed_val:
             parsed_val = raw_hex

        result.fields.append(DPTFieldValue(
            name=fdef.name,
            range_str=range_str,
            raw_hex=raw_hex,
            parsed_value=parsed_val,
            encoding=fdef.encoding or "Unsigned"
        ))

    def _parse_bit_fields(self, fdef: DPTFieldDef, chunk: bytes, result: DPTParseResult):
        # Convert chunk to integer
        # User specified: "如果是完整的字节则正常解析如果是不完整的字节则是需要解析对应bit此时是小端序"
        # Bit parsing context often implies Little Endian for bit indexing within bytes or across bytes in some definitions.
        val = int.from_bytes(chunk, byteorder='little', signed=False)

        # Sort bit fields by bit index
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
            # Extract bit value (Assuming bit_0 is LSB)
            bit_val = (val >> bit_idx) & 1

            current_byte_offset = fdef.byte_offset
            range_str = f"{current_byte_offset}/{bit_idx}"
            raw_hex = str(bit_val)
            parsed_val = str(bit_val)

            conversion = bit_def.get("conversion")
            if conversion:
                if isinstance(conversion, dict):
                    if conversion.get("type") == "linear":
                        # Linear on a bit? Possible.
                        res = float(conversion.get("resolution", 1.0))
                        off = float(conversion.get("offset", 0.0))
                        phy_val = bit_val * res + off
                        if phy_val.is_integer():
                            parsed_val = str(int(phy_val))
                        else:
                            parsed_val = f"{phy_val:.6f}".rstrip('0').rstrip('.')
                    else:
                        # Enum - strict mapping
                        val_str = str(bit_val)
                        if val_str in conversion:
                            parsed_val = conversion[val_str]
                elif isinstance(conversion, str):
                    # Unit string - only append if not empty
                    if conversion.strip().upper() != "NONE":
                        parsed_val = f"{bit_val} {conversion}"

            description = bit_def.get("description", "")

            result.fields.append(DPTFieldValue(
                name=description,
                range_str=range_str,
                raw_hex=raw_hex,
                parsed_value=parsed_val,
                encoding="Bit"
            ))


def parse_bytes_to_table_rows(
    data: Union[bytes, bytearray, Iterable[int]],
    field_defs: Iterable[DPTFieldDef],
) -> List[List[str]]:
    parser = DPTParser(list(field_defs))
    result = parser.parse_bytes(data)
    return result.to_table_rows()


