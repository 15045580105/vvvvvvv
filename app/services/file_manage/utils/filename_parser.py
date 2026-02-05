from typing import Dict, Optional
from datetime import datetime, timezone
import re


FILENAME_TIMESTAMP_REGEX = re.compile(r"(\d{8}_\d{6}|\d{10,13})")


def parse_filename_metadata(filename: str) -> Dict[str, Optional[str]]:
    """解析文件名中的 APPID 和时间戳元数据信息。"""
    # 1. 基础校验：如果文件名为空，返回全空对象
    if not filename:
        return {"appid": None, "create_time": None, "raw_ts": None, "raw": filename}

    # 2. 解析 APPID：尝试获取第一个下划线前的部分
    parts = filename.split("_")
    appid = parts[0] if parts and re.match(r"^[A-Za-z0-9]+$", parts[0]) else None

    # 3. 查找时间戳特征（YYYYMMDD_HHMMSS 或 epoch 时间戳）
    m = FILENAME_TIMESTAMP_REGEX.search(filename)
    create_time = None
    raw_ts = None
    if m:
        ts = m.group(1)
        # 4. 尝试解析日期格式 YYYYMMDD_HHMMSS
        if "_" in ts:
            try:
                # 生成 ISO 字符串（天真本地时间）——下游代码可能假定本地时区
                create_time = datetime.strptime(ts, "%Y%m%d_%H%M%S").isoformat()
                raw_ts = ts
            except Exception:
                create_time = None
        else:
            # 5. 尝试解析 epoch 秒或毫秒
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
