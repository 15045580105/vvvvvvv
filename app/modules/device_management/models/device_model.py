from PyQt5 import QtCore
from app.core.base_model import BaseModel


OFFLINE = "离线"
CONNECTING = "正在建链"
ONLINE = "建链成功"
DISCONNECTED = "已断链"
CONNECT_FAILED = "建链失败"


class DeviceModel(BaseModel):
    """设备模型: 维护设备列表并提供基础操作

    字段(存入 JSON 的结构)：
      name   设备名
      ip     IP地址
      port   SSH端口
      user   用户名
      password 密码
      type   设备类型

      以下为每种协议的连接详情信息，供界面显示使用：
      ssh_connect_status    SSH 协议当前状态(离线/建链成功/连接失败等)
      doip_connect_status   DoIP 协议当前状态
      someip_connect_status SomeIP 协议当前状态

      ssh_connect_info      SSH 连接详情(成功/失败信息等)
      doip_connect_info     DoIP 连接详情
      someip_connect_info   SomeIP 连接详情

    设备“在线/离线/失败”等不再使用统一的 status 字段，
    而是由各协议的 *_connect_status 和 *_connect_info 字段在
    Service/Controller 中维护，View 负责按字段内容渲染 UI。
    """

    def __init__(self, parent=None, seed_initial=True):
        super().__init__(parent)
        self.devices = []
        # 设备数据由 Controller 从配置加载
        self.refresh()

    def add_device(
        self,
        name: str,
        ip: str,
        port: int = 22,
        user: str = "root",
        password: str | None = None,
        dev_type: str = "其他",
    ):
        self.devices.append(
            {
                "name": name,
                "ip": ip,
                "port": port,
                "user": user,
                "password": password or "",
                "type": dev_type,
                # 各协议当前连接状态，默认离线
                "ssh_connect_status": OFFLINE,
                "doip_connect_status": OFFLINE,
                "someip_connect_status": OFFLINE,
                # 各协议连接详情(成功/失败信息)
                "ssh_connect_info": "",
                "doip_connect_info": "",
                "someip_connect_info": "",
            }
        )
        self.dataChanged.emit()

    def update_device(self, index: int, **fields):
        """修改设备信息（不允许修改 type）。"""
        if 0 <= index < len(self.devices):
            dev = self.devices[index]
            for k, v in fields.items():
                if k == "type":
                    continue
                dev[k] = v
            self.dataChanged.emit()

    def delete_device(self, index: int):
        if 0 <= index < len(self.devices):
            del self.devices[index]
            self.dataChanged.emit()

    # 以下旧的状态相关接口保留空壳，以免外部调用报错；
    # 实际状态逻辑已迁移到 Service / Controller 层按协议分别维护。

    def connect_device(self, index: int):
        """兼容旧接口: 不再直接修改统一 status 字段。"""
        if 0 <= index < len(self.devices):
            # 状态改由 DeviceService 按协议更新，
            # 这里仅触发一次 dataChanged 以便界面刷新。
            self.dataChanged.emit()

    def disconnect_device(self, index: int):
        """兼容旧接口: 不再直接修改统一 status 字段。"""
        if 0 <= index < len(self.devices):
            self.dataChanged.emit()

    def mark_connect_failed(self, index: int):
        """兼容旧接口: 不再直接修改统一 status 字段。"""
        if 0 <= index < len(self.devices):
            self.dataChanged.emit()

    def query_status(self, index: int):
        if 0 <= index < len(self.devices):
            # TODO: 真实状态查询由 Service 实现，并写回各协议的状态/详情字段
            self.dataChanged.emit()

    def remote_login(self, index: int):
        # TODO: 打开SSH/终端
        pass

    def refresh(self):
        now = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        for d in self.devices:
            d["last_refresh"] = now
            # 确保从旧配置加载的设备也至少带上新的状态/详情字段
            d.setdefault("ssh_connect_status", OFFLINE)
            d.setdefault("doip_connect_status", OFFLINE)
            d.setdefault("someip_connect_status", OFFLINE)
            d.setdefault("ssh_connect_info", "")
            d.setdefault("doip_connect_info", "")
            d.setdefault("someip_connect_info", "")
        self.dataChanged.emit()

    def to_list(self):
        """返回可序列化的设备列表结构，供配置持久化使用。"""
        return list(self.devices)

    def load_from_list(self, devices):
        """从列表批量加载设备。"""
        self.devices = list(devices or [])
        self.refresh()
