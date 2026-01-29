"""用于文件传输和 UI 模块的文件大小格式化辅助函数。

本模块提供一个单一的规范化 `format_size` 实现，确保项目中统一显示大小（避免重复实现）。

行为：
- 接受类整型的字节数或 None。
- 返回对人友好的字符串（例如 "0 B"、"512 B"、"1.0 KB"、"1.5 MB"）。
- 对负数大小谨慎处理（前面加上 '-'）。

请保持此函数精简且有良好测试；其他模块应导入它而不是重新实现相同的格式化逻辑。
"""

from typing import Optional


def format_size(size_bytes: Optional[int]) -> str:
    """返回可读的文件大小字符串，例如：0 B、1.0 KB、1.5 MB。

    参数：
        size_bytes: 字节数或 None。如果为 None，则视为 0。

    返回：
        格式化的大小字符串，对于 KB 及以上单位保留一位小数。
    """
    if size_bytes is None:
        return "0 B"
    try:
        size = int(size_bytes)
    except Exception:
        # 如果调用方传入了格式不正确的值，使用安全的回退值
        size = 0
    negative = size < 0
    size = abs(size)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    val = float(size)
    # 在 1024 的阈值下，将值缩放到合适的最大单位
    while val >= 1024.0 and i < len(units) - 1:
        val /= 1024.0
        i += 1
    # 对于字节显示整数，其他单位显示一位小数
    if i == 0:
        s = f"{int(val)} {units[i]}"
    else:
        s = f"{val:.1f} {units[i]}"
    return f"-{s}" if negative else s
