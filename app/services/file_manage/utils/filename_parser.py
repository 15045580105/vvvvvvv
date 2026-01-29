"""供 DownloadManager 和其他模块使用的文件名解析辅助函数。

本模块集中了解析设备生成文件名中元数据（如 APPID 和创建时间戳）的启发式规则。将此逻辑集中在此处便于测试与在命名规范变化时更新。

公共 API:
- parse_filename_metadata(filename: str) -> dict

说明:
- 解析器采用保守策略：缺失字段返回 None，遇到格式异常不会抛出异常。
- 支持的时间戳模式：
  - YYYYMMDD_HHMMSS（例如 20250620_080010）
  - epoch 秒（10 位）或毫秒（13 位及以上）
"""

from typing import Dict, Optional
from datetime import datetime, timezone
import re


FILENAME_TIMESTAMP_REGEX = re.compile(r"(\d{8}_\d{6}|\d{10,13})")


def parse_filename_metadata(filename: str) -> Dict[str, Optional[str]]:
    """从项目使用的文件名中解析已知元数据。

    返回包含可用键（例如 'appid'、'create_time'、'raw_ts'）的字典。
    函数采用保守策略：不会抛出异常，缺失字段返回 None。

    示例结果：
    >>> parse_filename_metadata('VCPS_20250620_080010.gz')
    {'appid': 'VCPS', 'create_time': '2025-06-20T08:00:10', 'raw_ts': '20250620_080010', 'raw': '...'}
    """
    if not filename:
        return {"appid": None, "create_time": None, "raw_ts": None, "raw": filename}

    # 尝试在第一个下划线之前提取类似 appid 的前缀（字母、数字、下划线）
    parts = filename.split("_")
    appid = parts[0] if parts and re.match(r"^[A-Za-z0-9]+$", parts[0]) else None

    # 查找类似 YYYYMMDD_HHMMSS 或 epoch（10-13 位数字）的时间戳
    m = FILENAME_TIMESTAMP_REGEX.search(filename)
    create_time = None
    raw_ts = None
    if m:
        ts = m.group(1)
        # 尝试解析 YYYYMMDD_HHMMSS
        if "_" in ts:
            try:
                # 生成 ISO 字符串（天真本地时间）——下游代码可能假定本地时区
                create_time = datetime.strptime(ts, "%Y%m%d_%H%M%S").isoformat()
                raw_ts = ts
            except Exception:
                create_time = None
        else:
            # epoch 秒或毫秒
            try:
                if len(ts) >= 13:
                    # 毫秒
                    t = int(ts) / 1000.0
                else:
                    t = int(ts)
                # 对来自 epoch 的时间戳使用带时区的 UTC ISO 格式
                create_time = datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat()
                raw_ts = ts
            except Exception:
                create_time = None

    return {"appid": appid, "create_time": create_time, "raw_ts": raw_ts, "raw": filename}
