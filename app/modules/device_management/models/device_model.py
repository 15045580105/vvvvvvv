# 设备模型类

from PyQt5 import QtCore

from app.core.base_model import BaseModel


class DeviceModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices = []  # list of dicts
        self.load_mock()

    def load_mock(self):
        self.devices = [
            {"name": "CCUA-主控制器", "ip": "192.168.1.100", "doip": "✅ 在线", "ssh": "✅ 已连接",
             "time": "2024-11-19 14:30:22"},
            {"name": "CCU0-实时核1", "ip": "192.168.1.101", "doip": "✅ 在线", "ssh": "✅ 已连接",
             "time": "2024-11-19 14:31:05"},
            {"name": "CCU1-实时核2", "ip": "192.168.1.102", "doip": "❌ 离线", "ssh": "⏏️ 断开", "time": "--"},
        ]
        self.dataChanged.emit()

    def refresh(self):
        # update timestamp of first device as sample
        now = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        if self.devices:
            self.devices[0]["time"] = now
        self.dataChanged.emit()
