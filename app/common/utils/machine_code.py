import hashlib
import uuid
import platform
import socket


def get_machine_code():
    """获取机器唯一标识码"""
    try:
        # 获取主机名
        hostname = socket.gethostname()

        # 获取MAC地址
        mac = uuid.getnode()

        # 获取系统信息
        system_info = platform.system() + platform.release()

        # 组合信息并生成hash
        machine_info = f"{hostname}-{mac}-{system_info}"
        machine_hash = hashlib.md5(machine_info.encode()).hexdigest()

        # 取前16位作为机器码
        machine_code = machine_hash[:16].upper()

        return machine_code

    except Exception as e:
        # 如果获取失败，返回默认值
        return "DEFAULT_MACHINE_CODE"