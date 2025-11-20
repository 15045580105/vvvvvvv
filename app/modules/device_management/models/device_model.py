#设备模型类
from enum import Enum
from app.core.base_model import BaseModel


class DeviceStatus(Enum):
    DISCONNECTED = "离线"
    CONNECTING = "连接中"
    CONNECTED = "在线"
    ERROR = "错误"


class DeviceModel(BaseModel):
    """设备数据模型"""

    def __init__(self):
        super().__init__()
        self.device_info = {
            'ip': '',
            'port': 22,
            'username': '',
            'password': '',
            'name': '',
            'type': '',
            'status': DeviceStatus.DISCONNECTED,
            'last_connected': None
        }

    @property
    def ip(self):
        return self.device_info['ip']

    @ip.setter
    def ip(self, value):
        self.update_data('ip', value)
        self.device_info['ip'] = value

    @property
    def status(self):
        return self.device_info['status']

    @status.setter
    def status(self, value):
        self.update_data('status', value)
        self.device_info['status'] = value
        if value == DeviceStatus.CONNECTED:
            self.device_info['last_connected'] = datetime.now()