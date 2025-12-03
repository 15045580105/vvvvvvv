from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Dict, Any, Union


# -----------------------------
# 数据结构
# -----------------------------


@dataclass
class DPTFieldDef:
    """单个信号/字段在 DPT 文件中的定义。

    这里只实现一个比较通用的定义：
    - name: 字段名
    - start_bit: 起始 bit（从 0 开始计数，0 表示第一个字节的最低位或最高位，视项目约定）
    - length: bit 长度
    - description: 文字说明
    - values: 可选的值映射表（例如 {0: "关闭", 1: "开启"}）

    真实项目里 DPT 一般会更复杂（字节序、信号类型、比例系数、偏移量等），
    这些可以在后续慢慢扩展，这里先留好字段。
    """

    name: str
    start_bit: int
    length: int
    description: str = ""
    values: Dict[int, str] = field(default_factory=dict)
    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None


@dataclass
class DPTFieldValue:
    """解析后的单个字段结果。"""

    name: str
    bit_range: str
    raw_bits: str
    raw_value: int
    physical_value: Union[int, float, str]
    description: str


@dataclass
class DPTParseResult:
    """一次解析的整体结果，可以直接给到 DID 模块的 model 使用。"""

    bytes_hex: str
    fields: List[DPTFieldValue] = field(default_factory=list)

    def to_table_rows(self) -> List[List[str]]:
        """转换为表格行，方便 DID 页面四列表格展示。

        默认四列含义：
        - 第 0 列：bit 位（例如 "0-3"）
        - 第 1 列：功能/信号名称
        - 第 2 列：二进制值
        - 第 3 列：状态（解析值 + 描述）
        """

        rows: List[List[str]] = []
        for f in self.fields:
            status_parts = [str(f.physical_value)]
            if f.description:
                status_parts.append(f"({f.description})")
            status = " ".join(status_parts)
            rows.append([
                f.bit_range,
                f.name,
                f.raw_bits,
                status,
            ])
        return rows


# -----------------------------
# 工具函数
# -----------------------------


def _bytes_to_bits(data: bytes) -> str:
    """将整段字节转换为二进制字符串，高位在前。

    例如: b"\x12\xA0" -> "0001001010100000" (两个字节共 16 位)。
    """

    return "".join(f"{b:08b}" for b in data)


def _slice_bits(bit_str: str, start_bit: int, length: int) -> str:
    """从整体 bit 串中截取 [start_bit, start_bit+length) 区间。"""

    end = start_bit + length
    if start_bit < 0 or end > len(bit_str):
        return ""
    return bit_str[start_bit:end]


def _bits_to_int(bits: str) -> int:
    return int(bits, 2) if bits else 0


# -----------------------------
# DPT 解析主入口
# -----------------------------


class DPTParser:
    """DPT 解析工具。

    目前实现思路：
    1. 在构造时加载/注入 DPT 字段定义列表（可以来自配置文件、数据库等）。
    2. 调用 `parse_bytes` 传入字节数组，返回 `DPTParseResult`。

    这里提供一个比较通用的实现，你可以在业务层根据具体 DPT 格式
    自行构造 `DPTFieldDef` 列表，再交给本解析器处理。
    """

    def __init__(self, fields: Iterable[DPTFieldDef]):
        self._fields: List[DPTFieldDef] = sorted(
            list(fields), key=lambda f: f.start_bit
        )

    # 方便后续根据 DID 编号等做筛选
    @classmethod
    def from_dict_config(cls, config: Dict[str, Any]) -> "DPTParser":
        """从一个简单的 dict 配置构造解析器。

        config 示例：
        {
            "fields": [
                {"name": "Signal1", "start_bit": 0, "length": 4, "description": "状态位"},
                {"name": "Signal2", "start_bit": 4, "length": 8, "factor": 0.5, "unit": "V"},
            ]
        }
        """

        fields: List[DPTFieldDef] = []
        for item in config.get("fields", []):
            fields.append(
                DPTFieldDef(
                    name=item["name"],
                    start_bit=int(item["start_bit"]),
                    length=int(item["length"]),
                    description=item.get("description", ""),
                    values=item.get("values", {}) or {},
                    factor=float(item.get("factor", 1.0)),
                    offset=float(item.get("offset", 0.0)),
                    unit=item.get("unit"),
                )
            )
        return cls(fields)

    def parse_bytes(self, data: Union[bytes, bytearray, Iterable[int]]) -> DPTParseResult:
        """解析一段字节数据，返回结构化结果。

        参数:
            data: 可以是 bytes、bytearray 或 int 可迭代对象（0-255）。

        返回:
            DPTParseResult，内部 `fields` 列表可直接用于页面展示。
        """

        if isinstance(data, (bytearray, list, tuple)):
            data_bytes = bytes(data)
        elif isinstance(data, bytes):
            data_bytes = data
        else:
            # 尝试把任意 Iterable[int] 转成 bytes
            data_bytes = bytes(int(x) & 0xFF for x in data)  # type: ignore[arg-type]

        bits = _bytes_to_bits(data_bytes)
        bytes_hex = " ".join(f"{b:02X}" for b in data_bytes)

        result = DPTParseResult(bytes_hex=bytes_hex)

        for fdef in self._fields:
            raw_bits = _slice_bits(bits, fdef.start_bit, fdef.length)
            raw_value = _bits_to_int(raw_bits)

            # 物理值计算: (raw * factor + offset)
            physical: Union[int, float, str]
            if fdef.factor != 1.0 or fdef.offset != 0.0:
                physical = raw_value * fdef.factor + fdef.offset
            else:
                physical = raw_value

            # 若有枚举值映射，则优先显示枚举文本
            if fdef.values and raw_value in fdef.values:
                physical = fdef.values[raw_value]

            # 单位拼接
            if isinstance(physical, (int, float)) and fdef.unit:
                physical = f"{physical}{fdef.unit}"

            bit_range = (
                f"{fdef.start_bit}"
                if fdef.length == 1
                else f"{fdef.start_bit}-{fdef.start_bit + fdef.length - 1}"
            )

            field_val = DPTFieldValue(
                name=fdef.name,
                bit_range=bit_range,
                raw_bits=raw_bits,
                raw_value=raw_value,
                physical_value=physical,
                description=fdef.description,
            )
            result.fields.append(field_val)

        return result


# -----------------------------
# 便捷函数：直接解析，返回表格行
# -----------------------------


def parse_bytes_to_table_rows(
    data: Union[bytes, bytearray, Iterable[int]],
    field_defs: Iterable[DPTFieldDef],
) -> List[List[str]]:
    """一次性完成: 使用字段定义解析字节，并返回四列表格行。

    方便 DID 界面直接调用，返回值格式：
        [
            ["bit位", "功能", "二进制值", "状态"],
            ...
        ]
    """

    parser = DPTParser(field_defs)
    result = parser.parse_bytes(data)
    return result.to_table_rows()
