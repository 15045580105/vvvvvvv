import logging
from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

from app.common.ui.modern_widgets import MessageToast, ModernConfirmDialog
from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.core.event_bus import event_bus
from app.modules.device_management.models.device_model import DeviceModel, OFFLINE, DISCONNECTED, CONNECT_FAILED
from app.modules.device_management.views.device_management_view import DeviceView
from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService


# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ConnectWorker(QThread):
    def __init__(self, service, device, log_signal=None):
        super().__init__()
        self.service = service
        self.device = device
        self.log_signal = log_signal

    def run(self):
        self.service.connect_device(self.device, log_signal=self.log_signal)


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
        # 重连请求信号
        self.device_service.reconnect_requested_signal.connect(self._on_reconnect_requested)

    def _on_reconnect_requested(self, device_info: dict, custom_log_signal=None):
        """处理来自 DeviceService 的重连请求"""
        target_ip = device_info.get("ip")
        target_port = int(device_info.get("port", 22))

        # 确定日志输出方式
        # custom_log_signal 是 LogConfigService.log_signal (PyQtBoundSignal)
        # 它有 emit 方法，可以用 log_signal.emit(msg)
        # 或者直接 connect(slot)
        log_func = None

        if custom_log_signal:
             if hasattr(custom_log_signal, 'emit'):
                 log_func = custom_log_signal.emit
             elif callable(custom_log_signal):
                 log_func = custom_log_signal

        if not log_func:
             # Fallback
             log_func = self.view.append_log
             # IMPORTANT: If custom_log_signal was invalid/None, ensure we don't pass garbage downstream
             custom_log_signal = None
        else:
             # Debug log to verify we are using custom signal
             # log_func(f"[DEBUG] Reconnect using custom log signal: {custom_log_signal}")
             pass

        # 查找设备索引
        index = -1
        for i, d in enumerate(self.model.devices):
            if d.get("ip") == target_ip and int(d.get("port", 22)) == target_port:
                index = i
                break
        if index == -1:
            log_func(f"重连未找到设备: {target_ip}:{target_port}")
            return

        log_func(f"收到重连请求，正在执行断开和重连流程: {self._device_repr(index)}")

        # 1. 执行断开逻辑
        # 注意: _do_disconnect 内部仅调用 service.disconnect_device 和 写日志
        # 我们暂时手动执行 service 断开，以便控制日志去向
        device = self.model.devices[index]
        self.device_service.disconnect_device(device, log_signal=custom_log_signal)
        log_func(f"断开连接 -> {self._device_repr(index)}")

        # 2. 强制清理客户端 (确保干净的重连环境)
        self.device_service.reset_connection_clients()
        log_func(f"正在执行重连: {self._device_repr(index)}，请等候30秒左右......")

        # 3. 延迟执行连接
        QTimer.singleShot(30000, lambda: self._do_connect(index, log_signal=custom_log_signal))


    def _safe_disconnect_log(self, custom_signal):
        # Deprecated: No longer needed as we pass log_signal explicitly
        pass

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
        event_bus.device_list_changed.emit()

    # -------------------- 设备添加 --------------------
    def _on_add_clicked(self):
        ip = self.view.ip_input.text().strip()
        port = self.view.port_input.text().strip() or "22"
        user = self.view.user_input.text().strip()
        password = self.view.password_input.text().strip()
        name = self.view.name_input.text().strip()
        dev_type = self.view.type_input.currentText()

        # New fields from the view update
        multicast_ip = self.view.multicast_ip_input.text().strip()
        multicast_port = self.view.multicast_port_input.text().strip()
        vlan_id = self.view.vlan_id_input.text().strip()
        client_port = self.view.client_port_input.text().strip()
        client_id = self.view.client_id_input.text().strip()

        if not ip:
            self.view.show_message("请输入IP地址", "warning")
            return

        device = {
            "ip": ip,
            "port": int(port),
            "user": user,
            "password": password,
            "name": name,
            "type": dev_type,
            "multicast_ip": multicast_ip,
            "multicast_port": multicast_port,
            "vlan_id": vlan_id,
            "client_port": client_port,
            "client_id": client_id,
            "ssh_connect_status": "未连接",
            "doip_connect_status": "未连接",
            "someip_connect_status": "未连接",
            "ssh_connect_info": "",
            "doip_connect_info": "",
            "someip_connect_info": ""
        }

        # Use unpacking to pass dictionary items as arguments
        self.model.add_device(**device)
        self._clear_inputs()
        self._persist_devices()
        self.on_model_changed()

    def _clear_inputs(self):
        self.view.ip_input.clear()
        self.view.port_input.setText("22")
        self.view.user_input.clear()
        self.view.password_input.clear()
        self.view.name_input.clear()
        self.view.type_input.setCurrentIndex(0)

        self.view.multicast_ip_input.setText("239.71.0.2")
        self.view.multicast_port_input.setText("30490")
        self.view.vlan_id_input.setText("4")
        self.view.client_port_input.setText("30813")
        self.view.client_id_input.setText("30813")

    def on_model_changed(self):
        self.view.populate(self.model.devices)
        self._bind_row_buttons()

    def _bind_row_buttons(self):
        """为当前表格中的每一行重新绑定操作按钮的信号。

        注意：视图中列序为：
        0 序号 / 1 设备名 / 2 设备类型 / 3 IP / 4 端口 / 5 控制器IP / 6 控制器端口 / 7 连接状态 / 8 详情 / 9 操作
        因此操作按钮容器位于列索引 9。
        """
        table = self.view.table
        row_count = table.rowCount()
        action_aliases = {
            "连接设备": ("连接设备", "连接", "connect"),
            "断开连接": ("断开连接", "断开", "disconnect"),
            "修改信息": ("修改信息", "修改", "edit"),
            "删除设备": ("删除设备", "删除", "delete"),
            "软件升级": ("软件升级", "升级", "upgrade"),
            "状态查询": ("状态查询", "查询", "query"),
        }
        for row in range(row_count):
            action_widget = table.cellWidget(row, 9)  # 修正为操作列索引 9
            if not action_widget:
                continue
            buttons = {}
            for child in action_widget.findChildren(QtWidgets.QAbstractButton):
                keys = {
                    child.text(),
                    child.property("full_text"),
                    child.property("compact_text"),
                    child.property("action_key"),
                    child.objectName(),
                }
                for key in keys:
                    if key:
                        buttons[str(key)] = child

            def _resolve_button(action_name: str):
                for alias in action_aliases.get(action_name, (action_name,)):
                    if alias in buttons:
                        return buttons[alias]
                return None

            connect_btn = _resolve_button("连接设备")
            disconnect_btn = _resolve_button("断开连接")
            edit_btn = _resolve_button("修改信息")
            delete_btn = _resolve_button("删除设备")
            upgrade_btn = _resolve_button("软件升级")
            query_btn = _resolve_button("状态查询")

            if connect_btn:
                connect_btn.clicked.connect(lambda _, r=row: self._do_connect(r))
            if disconnect_btn:
                disconnect_btn.clicked.connect(lambda _, r=row: self._do_disconnect(r))
            if edit_btn:
                edit_btn.clicked.connect(lambda _, r=row: self._do_edit(r))
            if delete_btn:
                delete_btn.clicked.connect(lambda _, r=row: self._do_delete(r))
            if upgrade_btn:
                upgrade_btn.clicked.connect(lambda _, r=row: self._do_upgrade(r))
            if query_btn:
                query_btn.clicked.connect(lambda _, r=row: self._do_query(r))

    def _do_edit(self, index: int):
        """设备信息修改：仅当设备当前 SSH 状态为“离线”时允许修改。

        可修改字段：设备名称、IP 地址、SSH 端口、用户名、密码；设备类型只读展示。
        """
        device = self.model.devices[index]
        ssh_status = str(device.get("ssh_connect_status", OFFLINE))
        doip_status = str(device.get("doip_connect_status", OFFLINE))
        someip_status = str(device.get("someip_connect_status", OFFLINE))
        # 所有协议都必须是离线或已断链才能建立连接
        # FIX: "连接失败" also should be allowed to edit/delete
        allowed = (OFFLINE, DISCONNECTED, CONNECT_FAILED, "连接失败") # Added CONNECT_FAILED and "连接失败"
        if ssh_status not in allowed or doip_status not in allowed or someip_status not in allowed:
            MessageToast(self.view).show_toast("仅在设备离线状态下允许修改信息", 1)
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

        # 新增/修改字段
        multicast_ip_edit = QtWidgets.QLineEdit(str(device.get("multicast_ip", "239.71.0.2")))
        multicast_port_edit = QtWidgets.QLineEdit(str(device.get("multicast_port", "30490")))
        vlan_id_edit = QtWidgets.QLineEdit(str(device.get("vlan_id", "4")))
        client_port_edit = QtWidgets.QLineEdit(str(device.get("client_port", "30813")))
        client_id_edit = QtWidgets.QLineEdit(str(device.get("client_id", "30813")))

        form.addRow("设备名:", name_edit)
        form.addRow("IP地址:", ip_edit)
        form.addRow("SSH端口:", port_edit)
        form.addRow("用户名:", user_edit)
        form.addRow("密码:", pwd_edit)
        form.addRow("设备类型(只读):", type_label)

        form.addRow("标准组播 IP:", multicast_ip_edit)
        form.addRow("标准组播端口:", multicast_port_edit)
        form.addRow("VLAN ID:", vlan_id_edit)
        form.addRow("客户端端口:", client_port_edit)
        form.addRow("客户端 ID:", client_id_edit)

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

        multicast_ip = multicast_ip_edit.text().strip()
        multicast_port = multicast_port_edit.text().strip()
        vlan_id = vlan_id_edit.text().strip()
        client_port = client_port_edit.text().strip()
        client_id = client_id_edit.text().strip()

        if not name or not ip:
            MessageToast(self.view).show_toast("设备名与IP不能为空", 1)
            return
        try:
            port = int(port_text)
        except ValueError:
            MessageToast(self.view).show_toast("端口必须为数字", 1)
            return

        self.model.update_device(
            index,
            name=name, ip=ip, port=port, user=user, password=pwd,
            multicast_ip=multicast_ip, multicast_port=multicast_port,
            vlan_id=vlan_id, client_port=client_port, client_id=client_id
        )
        self._persist_devices()
        self.on_model_changed()
        self.view.append_log(f"修改设备信息 -> {self._device_repr(index)}")

    def _device_repr(self, index):
        d = self.model.devices[index]
        return f"{d.get('name')} {d.get('ip')}:{d.get('port')}"

    # -------------------------------------连接/断开/删除等操作 -------------------------------------------------------------
    def _do_connect(self, index, log_signal=None):
        _log = log_signal.emit if log_signal else self.view.append_log
        _log(f"开始连接 -> {self._device_repr(index)}")
        device = self.model.devices[index]
        ssh_status = str(device.get("ssh_connect_status", OFFLINE))
        doip_status = str(device.get("doip_connect_status", OFFLINE))
        someip_status = str(device.get("someip_connect_status", OFFLINE))
        # 所有协议都必须是离线或已断链才能建立连接
        # FIX: Also allow if connection previously failed
        allowed = (OFFLINE, DISCONNECTED, CONNECT_FAILED, "连接失败")
        if ssh_status not in allowed or doip_status not in allowed or someip_status not in allowed:
            # If redirected log, just log it. If GUI interaction, maybe toast is still ok or log it.
            _log("仅在所有协议均为离线/已断链状态下可建立连接")
            if not log_signal:
                 MessageToast(self.view).show_toast("仅在所有协议均为离线/已断链状态下可建立连接", 1)
            return
        # 使用副本进行连接，避免多线程直接修改模型数据（虽然 Service 会发信号回来更新）
        device_copy = device.copy()

        # 启动后台线程进行连接，避免阻塞 UI 导致 Loading 动画卡顿
        worker = ConnectWorker(self.device_service, device_copy, log_signal=log_signal)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _cleanup_worker(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _do_disconnect(self, index):
        device = self.model.devices[index]

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
        # FIX: Also allow deletion if connection failed
        allowed = (OFFLINE, DISCONNECTED, CONNECT_FAILED, "连接失败")
        if ssh_status not in allowed or doip_status not in allowed or someip_status not in allowed:
            MessageToast(self.view).show_toast("仅在离线/已断链状态下允许删除设备", 1)
            return

        # 二次确认
        name = self._device_repr(index)
        dialog = ModernConfirmDialog(self.view, "确认删除", f"确定要删除设备 {name} 吗？", confirm_text="删除", is_danger=True)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
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
        logger.info(message)
