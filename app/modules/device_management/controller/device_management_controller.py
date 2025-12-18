from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal,QThread
from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.device_management.models.device_model import DeviceModel, OFFLINE, ONLINE, DISCONNECTED
from app.modules.device_management.views.device_management_view import DeviceView
from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService


class ConnectWorker(QThread):
    def __init__(self, service, device):
        super().__init__()
        self.service = service
        self.device = device

    def run(self):
        self.service.connect_device(self.device)


class DeviceController(BaseController):
    switch_page = pyqtSignal(dict, str)  # 通用页面切换信号：payload + 目标tab显示名

    def __init__(self, parent=None):
        # 初始化模型 & 视图
        self.model = DeviceModel(parent, seed_initial=False)
        self.view = DeviceView(parent)
        super().__init__(self.model, self.view, parent)
        # 业务服务
        # 尝试从容器获取，如果不存在则创建并注册
        self.device_service = di_container.resolve(DeviceService)
        if not self.device_service:
            self.device_service = DeviceService()
            di_container.register_singleton(DeviceService, self.device_service)

        self.config_service = ConfigService()
        self._progress_dialog: QtWidgets.QProgressDialog | None = None

        # 修复：初始化线程列表，防止 AttributeError
        self._workers = []

        self._connect_static_signals()
        self._initial_devices()
        # 首次刷新视图
        self.on_model_changed()

    def _connect_static_signals(self):
        self.view.add_btn.clicked.connect(self._on_add_clicked)
        self.device_service.log_signal.connect(self.update_log)
        # 协议状态变更信号，用于刷新三行状态和详情
        self.device_service.protocol_status_changed_signal.connect(self._on_protocol_status_changed)


    def _on_protocol_status_changed(self, device: dict):
        """当 DeviceService 报告协议状态变化时，更新模型中的对应设备并刷新界面与配置文件。

        约定 device 中可包含以下字段：
        - ip, port: 用于定位设备
        - ssh_connect_status / doip_connect_status / someip_connect_status: 协议当前状态
        - ssh_connect_info / doip_connect_info / someip_connect_info: 协议成功/失败详情

        Service 层只需要根据协议类型填写相应字段，其余字段保持不变，
        这里会将这些字段同步进模型 devices，并持久化到 JSON。
        """
        ip = device.get("ip")
        port = int(device.get("port", 22))
        for d in self.model.devices:
            if d.get("ip") == ip and int(d.get("port", 22)) == port:
                # 将传入 device 中的 *_connect_status 和 *_connect_info 同步到模型
                for key in (
                    "ssh_connect_status", "doip_connect_status", "someip_connect_status",
                    "ssh_connect_info", "doip_connect_info", "someip_connect_info",
                ):
                    if key in device:
                        d[key] = device[key]
                break
        # 持久化并刷新 UI
        self._persist_devices()
        self.on_model_changed()

    def _initial_devices(self):
        """从配置文件加载设备列表并刷新到视图。"""
        devices = self.config_service.load_devices() or []
        if devices:
            self.model.load_from_list(devices)
            self.view.append_log(f"已从配置加载 {len(devices)} 台设备")

    def _persist_devices(self):
        """将当前模型中的设备列表落盘到 JSON 配置文件。"""
        self.config_service.save_devices(self.model.to_list())

    # -------------------- 设备添加 --------------------
    def _on_add_clicked(self):
        name = self.view.name_input.text().strip()
        ip = self.view.ip_input.text().strip()
        port_text = self.view.port_input.text().strip() or "22"
        user = self.view.user_input.text().strip() or "root"
        password = self.view.password_input.text().strip()
        dev_type = self.view.type_input.currentText() or "其他"

        # 前置校验：名称和 IP 必填
        if not name or not ip:
            QtWidgets.QMessageBox.warning(self.view, "提示", "设备名与IP不能为空")
            return
        # 端口必须为数字
        try:
            port = int(port_text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self.view, "提示", "端口必须为数字")
            return

        # TODO: 可扩展为更严格的 IP 格式校验

        self.model.add_device(name, ip, port, user, password=password, dev_type=dev_type)
        self._persist_devices()
        self.view.append_log(f"添加设备: {name} ({ip}:{port}) [{dev_type}]")

        # 清空输入
        self.view.name_input.clear()
        self.view.ip_input.clear()
        self.view.port_input.clear()
        self.view.user_input.clear()
        self.view.password_input.clear()

    def on_model_changed(self):
        self.view.populate(self.model.devices)
        self._bind_row_buttons()

    def _bind_row_buttons(self):
        """为当前表格中的每一行重新绑定操作按钮的信号。

        注意：视图中列���序为：
        0 序号 / 1 设备名 / 2 设备类型 / 3 IP / 4 端口 / 5 连接状态 / 6 详情 / 7 操作
        因此操作按钮容器位于列索引 7。
        """
        table = self.view.table
        row_count = table.rowCount()
        for row in range(row_count):
            action_widget = table.cellWidget(row, 7)  # 修正为操作列索引 7
            if not action_widget:
                continue
            buttons = {}
            for child in action_widget.findChildren(QtWidgets.QAbstractButton):
                buttons[child.text()] = child
            if "连接设备" in buttons:
                buttons["连接设备"].clicked.connect(lambda _, r=row: self._do_connect(r))
            if "断开连接" in buttons:
                buttons["断开连接"].clicked.connect(lambda _, r=row: self._do_disconnect(r))
            if "修改信息" in buttons:
                buttons["修改信息"].clicked.connect(lambda _, r=row: self._do_edit(r))
            if "删除设备" in buttons:
                buttons["删除设备"].clicked.connect(lambda _, r=row: self._do_delete(r))
            if "软件升级" in buttons:
                buttons["软件升级"].clicked.connect(lambda _, r=row: self._do_upgrade(r))
            if "状态查询" in buttons:
                buttons["状态查询"].clicked.connect(lambda _, r=row: self._do_query(r))

    def _do_edit(self, index: int):
        """设备信息修改：仅当设备当前 SSH 状态为“离线”时允许修改。

        可修改字段：设备名称、IP 地址、SSH 端口、用户名、密码；设备类型只读展示。
        """
        device = self.model.devices[index]
        ssh_status = str(device.get("ssh_connect_status", OFFLINE))
        doip_status = str(device.get("doip_connect_status", OFFLINE))
        someip_status = str(device.get("someip_connect_status", OFFLINE))
        # 所有协议都必须是离线或已断链才能建立连接
        allowed = (OFFLINE, DISCONNECTED)
        if ssh_status not in allowed or doip_status not in allowed or someip_status not in allowed:
            QtWidgets.QMessageBox.warning(self.view, "提示", "仅在设备离线状态下允许修改信息")
            return

        dialog = QtWidgets.QDialog(self.view)
        dialog.setWindowTitle("修改设备信息")
        form = QtWidgets.QFormLayout(dialog)

        name_edit = QtWidgets.QLineEdit(device.get("name", ""))
        ip_edit = QtWidgets.QLineEdit(device.get("ip", ""))
        port_edit = QtWidgets.QLineEdit(str(device.get("port", 22)))
        user_edit = QtWidgets.QLineEdit(device.get("user", ""))
        pwd_edit = QtWidgets.QLineEdit(device.get("password", ""))
        pwd_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        type_label = QtWidgets.QLabel(device.get("type", "其他"))

        form.addRow("设备名:", name_edit)
        form.addRow("IP地址:", ip_edit)
        form.addRow("SSH端口:", port_edit)
        form.addRow("用户名:", user_edit)
        form.addRow("密码:", pwd_edit)
        form.addRow("设备类型(只读):", type_label)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        form.addRow(btn_box)

        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return

        name = name_edit.text().strip()
        ip = ip_edit.text().strip()
        port_text = port_edit.text().strip() or "22"
        user = user_edit.text().strip()
        pwd = pwd_edit.text().strip()

        if not name or not ip:
            QtWidgets.QMessageBox.warning(self.view, "提示", "设备名与IP不能为空")
            return
        try:
            port = int(port_text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self.view, "提示", "端口必须为数字")
            return

        self.model.update_device(index, name=name, ip=ip, port=port, user=user, password=pwd)
        self._persist_devices()
        self.on_model_changed()
        self.view.append_log(f"修改设备信息 -> {self._device_repr(index)}")

    def _device_repr(self, index):
        d = self.model.devices[index]
        return f"{d.get('name')} {d.get('ip')}:{d.get('port')}"

    # -------------------------------------连接/断开/删除等操作 -------------------------------------------------------------
    def _do_connect(self, index):
        self.view.append_log(f"开始连接 -> {self._device_repr(index)}")
        device = self.model.devices[index]
        ssh_status = str(device.get("ssh_connect_status", OFFLINE))
        doip_status = str(device.get("doip_connect_status", OFFLINE))
        someip_status = str(device.get("someip_connect_status", OFFLINE))
        # 所有协议都必须是离线或已断链才能建立连接
        allowed = (OFFLINE, DISCONNECTED, "连接失败")
        if ssh_status not in allowed or doip_status not in allowed or someip_status not in allowed:
            QtWidgets.QMessageBox.warning(
                self.view,
                "提示",
                "仅在所有协议均为离线/已断链状态下可建立连接"
            )
            return
        # 使用副本进行连接，避免多线程直接修改模型数据（虽然 Service 会发信号回来更新）
        device_copy = device.copy()

        # 启动后台线程进行连接，避免阻塞 UI 导致 Loading 动画卡顿
        worker = ConnectWorker(self.device_service, device_copy)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _cleanup_worker(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _do_disconnect(self, index):
        device = self.model.devices[index]
        # ssh_status = str(device.get("ssh_connect_status", OFFLINE))
        # # 只有 SSH 在线时才有必要断开
        # if ssh_status != ONLINE:
        #     QtWidgets.QMessageBox.information(self.view, "提示", "当前 SSH 未在线，无需断开")
        #     return

        # 调用 DeviceService.disconnect_device，内部处理三种协议断开并发出协议状态信号
        self.device_service.disconnect_device(device)

        # Model 的状态由 _on_protocol_status_changed 中回调同步，这里只做日志
        self._persist_devices()
        self.view.append_log(f"断开连接 -> {self._device_repr(index)}")

    def _do_delete(self, index):
        device = self.model.devices[index]
        # 设备删除前提：不处于任务执行中，这里简化为只能在 SSH / DoIP/ someIP 离线或已断链状态删除
        ssh_status = str(device.get("ssh_connect_status", OFFLINE))
        doip_status = str(device.get("doip_connect_status", OFFLINE))
        someip_status = str(device.get("someip_connect_status", OFFLINE))
        # 所有协议都必须是离线或断开才能建立连接
        allowed = (OFFLINE, DISCONNECTED)
        if ssh_status not in allowed or doip_status not in allowed or someip_status not in allowed:
            QtWidgets.QMessageBox.warning(self.view, "提示", "仅在离线/已断链状态下允许删除设备")
            return

        # 二次确认
        name = self._device_repr(index)
        ret = QtWidgets.QMessageBox.question(self.view, "确认删除", f"确定要删除设备 {name} 吗？", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ret != QtWidgets.QMessageBox.Yes:
            return

        self.model.delete_device(index)
        self._persist_devices()
        self.view.append_log(f"删除设备 -> {name}")

    def _do_upgrade(self, index):
        """软件升级操作：通过通用switch_page信号请求主窗口切换到“设备升级”页"""
        from app.common.ui.constants import PageConfig  # 延迟导入，避免循环
        if 0 <= index < len(self.model.devices):
            device = self.model.devices[index]
            payload = {"device": device}
            self.switch_page.emit(payload, PageConfig.PAGE_UPGRADE_DISPLAY)

    def _do_query(self, index):
        """状态查询：跳转到拓扑监控界面入口。
        这里调用占位方法 `open_topology_monitor`，由主窗口或路由逻辑实现真实跳转。
        """
        from app.common.ui.constants import PageConfig  # 延迟导入，避免循环
        if 0 <= index < len(self.model.devices):
            device = self.model.devices[index]
            payload = {"device": device}
            self.switch_page.emit(payload, PageConfig.PAGE_TOPOLOGY_DISPLAY)


    def on_close(self):
        """在应用关闭或模块卸载时调用，断开所有设备连接并重置状态/详情。
        调用顺序建议为：
        1. 通过 DeviceService 断开所有底层连接；
        2. 更新模型中每台设备的 *_connect_status 和 *_connect_info 字段；
        3. 持久化到 JSON，确保下次启动时为离线/已断链状态；
        """
        # 重置所有设备的状态和详情字段
        for dev in self.model.devices:
            dev["ssh_connect_status"] = DISCONNECTED
            dev["doip_connect_status"] = DISCONNECTED
            dev["someip_connect_status"] = DISCONNECTED
            dev["ssh_connect_info"] = "已断开"
            dev["doip_connect_info"] = "已断开"
            dev["someip_connect_info"] = "已断开"
        # 持久化并可选刷新视图（避免关闭前看到脏数据）
        self._persist_devices()
        self.on_model_changed()
        try:
            self.device_service.close_device_connections()
        except Exception as e:
            self.view.append_log(f"关闭设备连接时发生异常: {e}")

    # -------- 供其他模块调用的接口 --------------------------------
    def get_all_devices(self):
        """获取当前设备列表（原始 dict 列表）。"""
        return self.model.to_list()

    def get_ssh_online_devices(self):
        """获取 SSH 协议在线的设备列表。"""
        return [d for d in self.model.devices if str(d.get("ssh_connect_status", "")).find("在线") != -1]

    def get_doip_online_devices(self):
        """获取 DoIP 协议在线的设备列表。"""
        return [d for d in self.model.devices if str(d.get("doip_connect_status", "")).find("在线") != -1]

    def get_someip_online_devices(self):
        """获取 SomeIP 协议在线的设备列表。"""
        return [d for d in self.model.devices if str(d.get("someip_connect_status", "")).find("在线") != -1]

    def get_view(self):
        return self.view

    def update_log(self, message):
        self.view.append_log(message)
