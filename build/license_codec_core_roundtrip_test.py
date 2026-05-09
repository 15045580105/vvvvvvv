import json
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"D:\uidq9000\PycharmProjects\oneboxforgac")

from app.common.utils.license_codec_core import LicenseCodec
from app.common.utils.license_manager import decode_activation_code

codec = LicenseCodec()
now = datetime(2026, 5, 8, 12, 0, 0)
code = codec.generate(
    token="12345678-1234-5678-1234-567812345678",
    generate_time=now,
    expire_time=now + timedelta(days=30),
    license_days=30,
    expire_code_seconds=7200,
    activated_count=1,
    machine_id="A" * 64,
    name="张三",
    department="研发部",
    email="zhangsan@gac.com.cn",
)
decoded = decode_activation_code(code)
result = {
    "code_length": len(code),
    "machine_id": decoded.machine_id,
    "name": decoded.user_info.name,
    "department": decoded.user_info.department,
    "email": decoded.user_info.email,
    "license_days": decoded.license_days,
    "expire_code_seconds": decoded.expire_code_seconds,
    "activated_count": decoded.activated_count,
}
with open(r"D:\uidq9000\PycharmProjects\oneboxforgac\build\license_codec_core_roundtrip_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

