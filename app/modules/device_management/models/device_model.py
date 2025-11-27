from PyQt5 import QtCore
from app.core.base_model import BaseModel


class DeviceModel(BaseModel):
    """
    设备模型: 维护设备列表并提供基础操作
    字段:
      name 设备名
      ip   IP地址
      port SSH端口
      user 用户名
      status 当前连接状态: 未连接 / ✅ 已连接 / ⏏️ 已断开 / 升级中 / 查询中
    """
    def __init__(self, parent=None, seed_initial=True):
        super().__init__(parent)
        self.devices = []
        if seed_initial:
            self.seed_devices()
        self.refresh()

    def seed_devices(self):
        """初始化演示数据"""
        self.devices = [
            {"name": "aaa", "ip": "192.168.1.100", "port": 22, "user": "root", "status": "✅ 已连接"},
            {"name": "bbb", "ip": "192.168.1.101", "port": 22, "user": "root", "status": "⏏️ 升级中"},
            {"name": "ccc", "ip": "192.168.1.102", "port": 22, "user": "root", "status": "❌ 已断开"},
            {"name": "ddd", "ip": "192.168.1.150", "port": 2222, "user": "admin", "status": "🔗 未连接"},
        ]
        self.dataChanged.emit()

    def add_device(self, name: str, ip: str, port: int = 22, user: str = "root"):
        self.devices.append({
            "name": name,
            "ip": ip,
            "port": port,
            "user": user,
            "status": "未连接"
        })
        self.dataChanged.emit()

    def delete_device(self, index: int):
        if 0 <= index < len(self.devices):
            del self.devices[index]
            self.dataChanged.emit()

    def connect_device(self, index: int):
        if 0 <= index < len(self.devices):
            self.devices[index]["status"] = "✅ 已连接"
            self.dataChanged.emit()

    def disconnect_device(self, index: int):
        if 0 <= index < len(self.devices):
            self.devices[index]["status"] = "❌ 已断开"
            self.dataChanged.emit()

    def upgrade_device(self, index: int):
        if 0 <= index < len(self.devices):
            self.devices[index]["status"] = "⏏️ 升级中"
            # TODO: 真实升级流程
            self.dataChanged.emit()

    def query_status(self, index: int):
        if 0 <= index < len(self.devices):
            # TODO: 真实状态查询
            self.devices[index]["status"] = self.devices[index]["status"]
            self.dataChanged.emit()

    def remote_login(self, index: int):
        # TODO: 打开SSH/终端
        pass

    def refresh(self):
        now = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        for d in self.devices:
            d["last_refresh"] = now
        self.dataChanged.emit()
