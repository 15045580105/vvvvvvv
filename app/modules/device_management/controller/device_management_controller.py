import logging
import threading
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

from app.common.ui.modern_widgets import MessageToast, ModernConfirmDialog
from app.common.utils.worker import Worker
from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.core.event_bus import event_bus
from app.modules.device_management.models.device_model import DeviceModel, OFFLINE, DISCONNECTED, CONNECT_FAILED, CONNECTING
from app.modules.device_management.views.device_management_view import DeviceView, PasswordLineEdit
from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService


# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DeviceEditDialog(QtWidgets.QDialog):
    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改设备信息")
        self.setMinimumWidth(400)

        layout = QtWidgets.QVBoxLayout(self)

        tabs = QtWidgets.QTabWidget()

        # 基本信息 Tab
        base_tab = QtWidgets.QWidget()
        base_layout = QtWidgets.QFormLayout(base_tab)
        self.name_input = QtWidgets.QLineEdit(device.get("name", ""))
        self.type_input = QtWidgets.QComboBox()
        self.type_input.addItems(["ECU", "网关", "域控", "其他"])
        self.type_input.setCurrentText(device.get("type", "ECU"))
        base_layout.addRow("设备名：", self.name_input)
        base_layout.addRow("设备类型：", self.type_input)
        tabs.addTab(base_tab, "基本功能")

        # DoIP Tab
        doip_tab = QtWidgets.QWidget()
        doip_layout = QtWidgets.QFormLayout(doip_tab)
        self.doip_ip_input = QtWidgets.QLineEdit(device.get("doip_ip", ""))
        self.doip_port_input = QtWidgets.QLineEdit(str(device.get("doip_port", "13400")))
        doip_layout.addRow("DoIP IP：", self.doip_ip_input)
        doip_layout.addRow("DoIP 端口：", self.doip_port_input)

        def create_help_button(tooltip_text, btn_text):
            btn = QtWidgets.QPushButton(btn_text)
            btn.setToolTip(tooltip_text)
            btn.setFixedHeight(24)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #E5E7EB;
                    color: #4B5563;
                    border-radius: 12px;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 0px 10px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #D1D5DB;
                }
                QPushButton:pressed {
                    background-color: #9CA3AF;
                }
            """)
            return btn

        doip_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_doip_adv = create_help_button("Doip层高级配置", "DoIP ⚙")
        self.btn_doip_adv.clicked.connect(lambda: self._open_settings("doip"))
        self.btn_diag_adv = create_help_button("诊断层高级配置", "诊断 ⚙")
        self.btn_diag_adv.clicked.connect(lambda: self._open_settings("diag_layer"))
        doip_btn_layout.addWidget(QtWidgets.QLabel("高级配置："))
        doip_btn_layout.addWidget(self.btn_doip_adv)
        doip_btn_layout.addWidget(self.btn_diag_adv)
        doip_btn_layout.addStretch()
        doip_layout.addRow(doip_btn_layout)

        tabs.addTab(doip_tab, "DoIP")

        # SomeIP Tab
        someip_tab = QtWidgets.QWidget()
        someip_layout = QtWidgets.QFormLayout(someip_tab)
        self.someip_ip_input = QtWidgets.QLineEdit(device.get("someip_ip", ""))
        self.multicast_ip_input = QtWidgets.QLineEdit(device.get("multicast_ip", "239.71.0.2"))
        self.multicast_port_input = QtWidgets.QLineEdit(str(device.get("multicast_port", "30490")))
        self.vlan_id_input = QtWidgets.QLineEdit(str(device.get("vlan_id", "4")))
        self.client_port_input = QtWidgets.QLineEdit(str(device.get("client_port", "30813")))
        self.client_id_input = QtWidgets.QLineEdit(str(device.get("client_id", "30813")))
        someip_layout.addRow("SomeIP IP：", self.someip_ip_input)
        someip_layout.addRow("标准组播 IP：", self.multicast_ip_input)
        someip_layout.addRow("标准组播端口：", self.multicast_port_input)
        someip_layout.addRow("VLAN ID：", self.vlan_id_input)
        someip_layout.addRow("客户端端口：", self.client_port_input)
        someip_layout.addRow("客户端 ID：", self.client_id_input)

        someip_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_someip_adv = create_help_button("someip高级配置", "SomeIP ⚙")
        self.btn_someip_adv.clicked.connect(lambda: self._open_settings("someip"))
        someip_btn_layout.addWidget(QtWidgets.QLabel("高级配置："))
        someip_btn_layout.addWidget(self.btn_someip_adv)
        someip_btn_layout.addStretch()
        someip_layout.addRow(someip_btn_layout)

        tabs.addTab(someip_tab, "SomeIP")

        # SSH Tab
        ssh_tab = QtWidgets.QWidget()
        ssh_layout = QtWidgets.QFormLayout(ssh_tab)
        self.ssh_ip_input = QtWidgets.QLineEdit(device.get("ssh_ip", ""))
        self.ssh_port_input = QtWidgets.QLineEdit(str(device.get("ssh_port", "22")))
        self.user_input = QtWidgets.QLineEdit(device.get("user", ""))
        self.password_input = PasswordLineEdit(device.get("password", ""))
        ssh_layout.addRow("SSH IP：", self.ssh_ip_input)
        ssh_layout.addRow("SSH 端口：", self.ssh_port_input)
        ssh_layout.addRow("用户名：", self.user_input)
        ssh_layout.addRow("密码：", self.password_input)
        tabs.addTab(ssh_tab, "SSH")

        layout.addWidget(tabs)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _open_settings(self, page_id: str):
        main_win = self.parent().window() if self.parent() else None
        if main_win and hasattr(main_win, "show_settings_dialog"):
            main_win.show_settings_dialog(page_id)
            if hasattr(main_win, "settings_controller") and main_win.settings_controller:
                # 修复可能被模态对话框遮挡/无法点击的问题
                from PyQt5 import QtCore
                view = main_win.settings_controller.view
                view.setWindowModality(QtCore.Qt.ApplicationModal)
                view.setWindowFlags(view.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
                view.show()
                view.raise_()
                view.activateWindow()

    def get_data(self):
        return {
            "name": self.name_input.text().strip(),
            "doip_ip": self.doip_ip_input.text().strip(),
            "doip_port": int(self.doip_port_input.text().strip() or "13400"),
            "someip_ip": self.someip_ip_input.text().strip(),
            "multicast_ip": self.multicast_ip_input.text().strip(),
            "multicast_port": self.multicast_port_input.text().strip(),
            "vlan_id": self.vlan_id_input.text().strip(),
            "client_port": self.client_port_input.text().strip(),
            "client_id": self.client_id_input.text().strip(),
            "ssh_ip": self.ssh_ip_input.text().strip(),
            "ssh_port": int(self.ssh_port_input.text().strip() or "22"),
            "user": self.user_input.text().strip(),
            "password": self.password_input.text().strip(),
            "ip": self.doip_ip_input.text().strip() or self.someip_ip_input.text().strip() or self.ssh_ip_input.text().strip(),
            "port": int(self.ssh_port_input.text().strip() or "22"),
        }


class ConnectWorker(QThread):
    def __init__(self, service, device, log_signal=None, *, startup_auto_reconnect=False, reconnect=False, attempt_id=None):
        super().__init__()
        self.service = service
        self.device = device
        self.log_signal = log_signal
        self.startup_auto_reconnect = startup_auto_reconnect
        self.reconnect = reconnect
        self.attempt_id = attempt_id
        self.cancel_event = threading.Event()

    def cancel(self, current_device=None):
        self.cancel_event.set()
        self.service.request_cancel_connection(
            current_device or self.device,
            log_signal=self.log_signal,
            attempt_id=self.attempt_id,
        )

    def run(self):
        self.service.connect_device(
            self.device,
            log_signal=self.log_signal,
            cancel_event=self.cancel_event,
            reconnect=self.reconnect,
            attempt_id=self.attempt_id,
        )


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

        self._workers = []
        self._active_connect_worker: ConnectWorker | None = None
        self._active_connect_index: int | None = None
        self._startup_reconnect_done = False
        self._startup_reconnect_device_key = None
        self._startup_reconnect_failure_toast_shown = False
        self._startup_reconnect_protocols = []
        self._connect_attempt_seq = 0
        self._device_attempt_ids = {}
        self._shown_interface_warning_attempts = set()
        self._disconnecting_device_keys = set()
        self._pending_refresh = False
        self._pending_persist = False
        self._refresh_timer = QTimer(self.view)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(80)
        self._refresh_timer.timeout.connect(self._flush_pending_view_refresh)
        self._persist_timer = QTimer(self.view)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(180)
        self._persist_timer.timeout.connect(self._flush_pending_persist)

        # 连接超时看门狗：防止连接卡死导致 UI 不可操作
        self._connect_timeout_timer = QTimer(self.view)
        self._connect_timeout_timer.setSingleShot(True)
        self._connect_timeout_timer.setInterval(15000)  # 60秒超时
        self._connect_timeout_timer.timeout.connect(self._on_connect_timeout)

        self._connect_static_signals()
        self._initial_devices()
        # 首次刷新视图
        self.on_model_changed()
        # 已取消自动重连机制，每次启动需用户手动连接
        # self._schedule_startup_auto_reconnect()

    def _connect_static_signals(self):
        self.view.add_btn.clicked.connect(self._on_add_clicked)
        self.view.log_link_clicked.connect(self._on_log_link_clicked)
        self.device_service.log_signal.connect(self.update_log)
        # 协议状态变更信号，用于刷新三行状态和详情
        self.device_service.protocol_status_changed_signal.connect(self._on_protocol_status_changed)
        # 重连请求信号
        self.device_service.reconnect_requested_signal.connect(self._on_reconnect_requested)

        # 绑定工具栏按钮
        self.view.toolbar_doip_btn.clicked.connect(lambda: self._handle_toolbar_action("doip"))
        self.view.toolbar_ssh_btn.clicked.connect(lambda: self._handle_toolbar_action("ssh"))
        self.view.toolbar_someip_btn.clicked.connect(lambda: self._handle_toolbar_action("someip"))
        self.view.toolbar_edit_btn.clicked.connect(lambda: self._handle_toolbar_action("edit"))
        self.view.toolbar_delete_btn.clicked.connect(lambda: self._handle_toolbar_action("delete"))
        self.view.toolbar_upgrade_btn.clicked.connect(lambda: self._handle_toolbar_action("upgrade"))
        self.view.toolbar_query_btn.clicked.connect(lambda: self._handle_toolbar_action("query"))

    def _handle_toolbar_action(self, action: str):
        row = self.view.table.currentRow()
        # 仅有一台设备时自动关联唯一设备，无需用户手动选中
        if row < 0 and len(self.model.devices) == 1:
            row = 0
        if row < 0:
            return
        if action == "doip":
            self._handle_protocol_action(row, "doip", self.view.toolbar_doip_btn.text())
        elif action == "ssh":
            self._handle_protocol_action(row, "ssh", self.view.toolbar_ssh_btn.text())
        elif action == "someip":
            self._handle_protocol_action(row, "someip", self.view.toolbar_someip_btn.text())
        elif action == "edit":
            self._do_edit(row)
        elif action == "delete":
            self._do_delete(row)
        elif action == "upgrade":
            self._do_upgrade(row)
        elif action == "query":
            self._do_query(row)

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

        log_func(f"收到重连请求，开始异步重连: {self._device_repr(index)}")
        self._do_connect(index, log_signal=custom_log_signal, reconnect=True)


    def _safe_disconnect_log(self, custom_signal):
        # Deprecated: No longer needed as we pass log_signal explicitly
        pass

    def _on_protocol_status_changed(self, device: dict):
        """当 DeviceService 报告协议状态变化时，更新模型中的对应设备并刷新界面与配置文件。

        匹配策略（优先级从高到低）：
        1. 通过 _device_index（设备在列表中的索引）精确匹配 —— 解决同 IP 多设备问题
        2. 通过 ip + port 回退匹配 —— 兼容旧逻辑
        """
        ip = device.get("ip")
        port = int(device.get("port", 22))
        device_index = device.get("_device_index")
        target_key = f"{ip}:{port}"
        payload_attempt_id = device.get("_attempt_id")
        payload_generation = device.get("_connection_generation")

        # 优先通过 device_index 确定目标设备，避免同 IP 误匹配
        matched_device = None
        if device_index is not None and 0 <= device_index < len(self.model.devices):
            matched_device = self.model.devices[device_index]
            target_key = f"{matched_device.get('ip', ip)}:{matched_device.get('port', port)}"

        current_attempt_id = self._device_attempt_ids.get(target_key)

        logger.info(
            "[连接上下文] 设备状态回写 -> %s (index=%s) | attempt=%s | generation=%s | ssh=%s | doip=%s | someip=%s",
            target_key,
            device_index,
            payload_attempt_id,
            payload_generation,
            device.get("ssh_connect_status"),
            device.get("doip_connect_status"),
            device.get("someip_connect_status"),
        )

        if payload_attempt_id is not None and current_attempt_id is not None and payload_attempt_id != current_attempt_id:
            self.view.append_log(
                f"忽略过期连接状态回写 -> {target_key} | payload_attempt={payload_attempt_id} | current_attempt={current_attempt_id}"
            )
            return

        diagnostic = device.get("_doip_diagnostic") or {}
        if diagnostic.get("need_check_interface"):
            warn_key = (target_key, payload_attempt_id)
            if warn_key not in self._shown_interface_warning_attempts:
                self._shown_interface_warning_attempts.add(warn_key)
                local_ip = diagnostic.get("local_ip") or "--"
                interface_name = diagnostic.get("interface_name") or "当前网卡"
                target_ip_text = diagnostic.get("target_ip") or ip or "--"
                warning_text = (
                    f"检测到本机网络接口 {interface_name} ({local_ip}) 与设备 {target_ip_text} 不在同一网段，"
                    f"请检查本机网络接口，并进入软件设置中的 DoIP 网络接口配置。"
                )
                self.view.append_log(warning_text)
                self.view.append_link_log(
                    "快速处理：",
                    "打开 软件设置 > DoIP 设置",
                    "onebox://settings/doip?focus=network_interface",
                )
                MessageToast(self.view).show_toast("检测到网络接口可能配置异常，请点击操作日志中的蓝色链接处理", 1)

        # 如果未通过 index 匹配到，则回退到 ip+port 匹配
        if matched_device is None:
            for d in self.model.devices:
                if d.get("ip") == ip and int(d.get("port", 22)) == port:
                    matched_device = d
                    break

        if matched_device is not None:
            # 将传入 device 中的 *_connect_status 和 *_connect_info 同步到模型
            for key in (
                "ssh_connect_status", "doip_connect_status", "someip_connect_status",
                "ssh_connect_info", "doip_connect_info", "someip_connect_info",
            ):
                if key in device:
                    matched_device[key] = device[key]


        self._schedule_devices_persist()
        self._schedule_view_refresh()

    def _initial_devices(self):
        """从配置文件加载设备列表并刷新到视图。"""
        devices = self.config_service.load_devices() or []
        if devices:
            # 清理旧配置中可能残留的 CONNECTING 状态，避免界面卡死
            for dev in devices:
                for proto in ("doip", "ssh", "someip"):
                    if dev.get(f"{proto}_connect_status") == CONNECTING:
                        dev[f"{proto}_connect_status"] = DISCONNECTED
                        dev[f"{proto}_connect_info"] = "已断开"
                # 清理旧配置中的 _last_connected_protocols 字段
                dev.pop("_last_connected_protocols", None)
            self.model.load_from_list(devices)
            self.view.append_log(f"已从配置加载 {len(devices)} 台设备")

    def _schedule_startup_auto_reconnect(self):
        if self._startup_reconnect_done:
            return
        self._startup_reconnect_done = True
        QTimer.singleShot(300, self._auto_reconnect_from_saved_status)

    def _auto_reconnect_from_saved_status(self):
        """启动时自动重连：遍历所有设备，仅重连上次关闭时已建链的协议。"""
        for index, device in enumerate(self.model.devices):
            if not self._should_auto_reconnect(device):
                continue

            # 优先读取关闭时保存的已连接协议列表
            protocols_to_reconnect = []
            last_connected = device.get("_last_connected_protocols")
            if last_connected:
                protocols_to_reconnect = list(last_connected)
            else:
                # 异常退出时状态未被重置，仅重连真正已建链成功的协议
                for proto in ("doip", "ssh", "someip"):
                    if self._is_connected_like_status(device.get(f"{proto}_connect_status", OFFLINE)):
                        protocols_to_reconnect.append(proto)

            if not protocols_to_reconnect:
                # 没有协议需要重连，但可能有残留的 CONNECTING 状态需要清理
                cleaned = False
                for proto in ("doip", "ssh", "someip"):
                    if device.get(f"{proto}_connect_status") == CONNECTING:
                        device[f"{proto}_connect_status"] = DISCONNECTED
                        device[f"{proto}_connect_info"] = "已断开"
                        cleaned = True
                if cleaned:
                    self._persist_devices()
                    self.on_model_changed()
                continue

            proto_names = ", ".join(p.upper() for p in protocols_to_reconnect)
            self.view.append_log(f"启动时检测到上一次已建链的协议: {proto_names}，开始自动重连")
            self._startup_reconnect_device_key = self._device_key(self.model.devices[index])
            self._startup_reconnect_failure_toast_shown = False
            self._startup_reconnect_protocols = protocols_to_reconnect

            # 注意：_last_connected_protocols 不在这里 pop，而是等连接成功后在 _on_protocol_status_changed 中清理
            # 这样可以避免连接失败后残留 CONNECTING 状态无法被识别为需要重连

            self._mark_startup_auto_reconnecting(index, protocols_to_reconnect)
            self.view.append_log(f"启动自动重连 -> {self._device_repr(index)} [{proto_names}]")
            self._do_connect(index, startup_auto_reconnect=True)


    def _mark_startup_auto_reconnecting(self, index: int, protocols: list):
        """仅将需要自动重连的协议标记为 CONNECTING，其余协议强制重置为已断开。
        这样可以确保：
        1. 只有上次关闭时真正建链成功的协议才会被重连
        2. 其他协议（即使配置中有 IP）不会显示“正在建链”
        3. 避免旧配置文件残留状态导致界面卡死
        """
        if index < 0 or index >= len(self.model.devices):
            return
        device = self.model.devices[index]
        detail_text = "启动阶段自动重连中，正在建立连接"
        
        # 1. 标记需要重连的协议为 CONNECTING
        for proto in protocols:
            device[f"{proto}_connect_status"] = CONNECTING
            device[f"{proto}_connect_info"] = detail_text
        
        # 2. 强制将所有不在重连列表中的协议重置为 DISCONNECTED
        # 这样可以确保：只连了 DoIP 的设备，SSH/SomeIP 不会显示“正在建链”
        for proto in ("doip", "ssh", "someip"):
            if proto not in protocols:
                device[f"{proto}_connect_status"] = DISCONNECTED
                device[f"{proto}_connect_info"] = "已断开"
        
        self._persist_devices()
        self.on_model_changed()

    def _next_connect_attempt_id(self, device: dict) -> int:
        self._connect_attempt_seq += 1
        attempt_id = self._connect_attempt_seq
        device_key = self._device_key(device)
        self._device_attempt_ids[device_key] = attempt_id
        self._shown_interface_warning_attempts = {
            item for item in self._shown_interface_warning_attempts if item[0] != device_key
        }
        return attempt_id

    def _schedule_view_refresh(self):
        self._pending_refresh = True
        self._refresh_timer.start()

    def _flush_pending_view_refresh(self):
        if not self._pending_refresh:
            return
        self._pending_refresh = False
        self.on_model_changed()

    def _schedule_devices_persist(self):
        self._pending_persist = True
        self._persist_timer.start()

    def _flush_pending_persist(self):
        if not self._pending_persist:
            return
        self._pending_persist = False
        self._persist_devices()

    def _mark_device_connecting(self, index: int, detail_text: str):
        if index < 0 or index >= len(self.model.devices):
            return
        device = self.model.devices[index]
        for protocol in ("ssh", "doip", "someip"):
            device[f"{protocol}_connect_status"] = CONNECTING
            device[f"{protocol}_connect_info"] = detail_text
        self._persist_devices()
        self.on_model_changed()

    def _append_startup_reconnect_failure_semantics(self, device: dict):
        field_pairs = [
            ("ssh_connect_status", "ssh_connect_info"),
            ("doip_connect_status", "doip_connect_info"),
            ("someip_connect_status", "someip_connect_info"),
        ]
        for status_key, info_key in field_pairs:
            status_text = str(device.get(status_key, "")).strip()
            info_text = str(device.get(info_key, "") or "").strip()
            if "连接失败" in status_text and "自动重连失败" not in info_text:
                device[info_key] = f"{info_text}（自动重连失败）" if info_text else "自动重连失败"

    def _notify_startup_reconnect_failure_once(self, device: dict):
        if self._startup_reconnect_failure_toast_shown:
            return
        statuses = [
            str(device.get("ssh_connect_status", "")).strip(),
            str(device.get("doip_connect_status", "")).strip(),
            str(device.get("someip_connect_status", "")).strip(),
        ]
        if any("连接失败" in status for status in statuses):
            self._startup_reconnect_failure_toast_shown = True
            MessageToast(self.view).show_toast("设备自动重连失败，请手动重试", 1)
            self.view.append_log("启动自动重连失败，请手动重试")

    # -------------------- 设备添加 --------------------
    def _on_add_clicked(self):
        name = self.view.name_input.text().strip()
        dev_type = self.view.type_input.currentText()

        doip_ip = self.view.doip_ip_input.text().strip()
        doip_port = self.view.doip_port_input.text().strip() or "13400"

        someip_ip = self.view.someip_ip_input.text().strip()
        multicast_ip = self.view.multicast_ip_input.text().strip()
        multicast_port = self.view.multicast_port_input.text().strip()
        vlan_id = self.view.vlan_id_input.text().strip()
        client_port = self.view.client_port_input.text().strip()
        client_id = self.view.client_id_input.text().strip()

        ssh_ip = self.view.ssh_ip_input.text().strip()
        ssh_port = self.view.ssh_port_input.text().strip() or "22"
        user = self.view.user_input.text().strip()
        password = self.view.password_input.text().strip()

        if not name:
            self.view.show_message("请输入设备名", "warning")
            return
        if not doip_ip and not ssh_ip and not someip_ip:
            self.view.show_message("请至少输入一种协议的IP地址", "warning")
            return

        device = {
            "name": name,
            "type": dev_type,
            "doip_ip": doip_ip,
            "doip_port": int(doip_port),
            "someip_ip": someip_ip,
            "multicast_ip": multicast_ip,
            "multicast_port": multicast_port,
            "vlan_id": vlan_id,
            "client_port": client_port,
            "client_id": client_id,
            "ssh_ip": ssh_ip,
            "ssh_port": int(ssh_port),
            "user": user,
            "password": password,
            "ssh_connect_status": "未连接",
            "doip_connect_status": "未连接",
            "someip_connect_status": "未连接",
            "ssh_connect_info": "",
            "doip_connect_info": "",
            "someip_connect_info": "",
            # Backward defaults mappings
            "ip": doip_ip or someip_ip or ssh_ip,
            "port": int(ssh_port),
        }

        # Use unpacking to pass dictionary items as arguments
        self.model.add_device(**device)
        self._clear_inputs()
        self._persist_devices()
        self.on_model_changed()

    def _clear_inputs(self):
        self.view.name_input.clear()
        self.view.type_input.setCurrentIndex(0)

        self.view.doip_ip_input.clear()
        self.view.doip_port_input.setText("13400")

        self.view.someip_ip_input.clear()
        self.view.multicast_ip_input.setText("239.71.0.2")
        self.view.multicast_port_input.setText("30490")
        self.view.vlan_id_input.setText("4")
        self.view.client_port_input.setText("30813")
        self.view.client_id_input.setText("30813")

        self.view.ssh_ip_input.clear()
        self.view.ssh_port_input.setText("22")
        self.view.user_input.clear()
        self.view.password_input.clear()

    def on_model_changed(self):
        self.view.populate(self.model.devices)
        self._bind_row_buttons()

    def _bind_row_buttons(self):
        pass

    def _handle_protocol_action(self, index: int, protocol: str, btn_text: str):
        if "断开" in btn_text:
            self._do_disconnect_protocol(index, protocol)
        else:
            self._do_connect_protocol(index, protocol)

    def _do_connect_protocol(self, index: int, protocol: str):
        device = self.model.devices[index]

        # 检查是否已有其他设备正在连接或已连接该协议
        for i, d in enumerate(self.model.devices):
            if i == index:
                continue
            status = str(d.get(f"{protocol}_connect_status", OFFLINE))
            if self._is_connected_like_status(status) or "连接中" in status or status == CONNECTING:
                protocol_name = protocol.upper()
                conflict_name = d.get('name', '未知')
                msg = (
                    f"{protocol_name} 协议已有设备（{conflict_name}）{'连接中' if ('连接中' in status or status == CONNECTING) else '已连接'}，"
                    f"每个协议同时只允许有一个连接！\n"
                    f"如需连接当前设备，请先断开（{conflict_name}）的 {protocol_name} 连接。"
                )
                self.view.append_log(msg)
                MessageToast(self.view).show_toast(msg, 2)
                return

        if protocol == "ssh":
            doip_status = str(device.get("doip_connect_status", OFFLINE))
            if "建链成功" not in doip_status and "在线" not in doip_status:
                msg = "SSH 依赖 DoIP，请先连接 DoIP 并在其建链成功后再连接 SSH！"
                self.view.append_log(msg)
                MessageToast(self.view).show_toast(msg, 1)
                return

        self._do_connect(index, log_signal=None, reconnect=False, connect_protocol=protocol)

    def _do_disconnect_protocol(self, index: int, protocol: str):
        device = self.model.devices[index]
        self.view.append_log(f"断开 {protocol.upper()} -> {self._device_repr(index)}")
        MessageToast(self.view).show_toast(f"正在断开 {protocol.upper()}，请稍候...", 0)

        def task():
            return self.device_service.disconnect_device(device.copy(), disconnect_protocol=protocol)

        worker = Worker(task)

        def on_finished(result):
            device_key = self._device_key(device)
            self._disconnecting_device_keys.discard(device_key)
            self._flush_pending_persist()
            self._flush_pending_view_refresh()

            if not isinstance(result, dict):
                MessageToast(self.view).show_toast("断开连接失败，请检查日志", 1)
                self.view.append_log(f"断开连接失败 -> {self._device_repr(index)}")
                return

            if result.get("all_already_disconnected"):
                MessageToast(self.view).show_toast("该设备当前已是断开状态", 0)
                return

            disconnected_protocols = result.get("disconnected_protocols") or []
            skipped_protocols = result.get("skipped_protocols") or []

            summary_parts = []
            if disconnected_protocols:
                summary_parts.append(f"已断开: {', '.join(disconnected_protocols).upper()}")
            if skipped_protocols:
                summary_parts.append(f"已是断开状态，跳过: {', '.join(skipped_protocols).upper()}")

            summary_text = "；".join(summary_parts) if summary_parts else "断开连接完成"
            MessageToast(self.view).show_toast("断开连接成功", 0)
            self.view.append_log(f"断开连接 -> {self._device_repr(index)}；{summary_text}")

        worker.result_signal.connect(on_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _is_connect_worker_running(self) -> bool:
        return bool(self._active_connect_worker and self._active_connect_worker.isRunning())
    
    def _guard_connect_sensitive_action(self, action_name: str, *, index: int | None = None) -> bool:
        if not self._is_connect_worker_running():
            return False
    
        # 如果是对同一个设备再次发起连接，自动取消卡住的旧连接
        if index is not None and self._active_connect_index == index and action_name == "连接设备":
            self.view.append_log(f"检测到连接卡住，自动取消旧连接 -> {self._device_repr(index)}")
            self._cancel_active_connect_worker()
            return False
    
        if index is not None and self._active_connect_index == index:
            message = f"设备正在连接中，暂不允许{action_name}，可点击【断开连接】中断当前连接"
        else:
            target_text = self._device_repr(self._active_connect_index) if self._active_connect_index is not None else "当前设备"
            message = f"{target_text} 正在连接中，暂不允许{action_name}，请等待完成或先点击【断开连接】"
    
        MessageToast(self.view).show_toast(message, 1)
        self.view.append_log(message)
        return True
    
    def _cancel_active_connect_worker(self):
        """取消当前正在运行的连接 worker，并重置相关状态。"""
        worker = self._active_connect_worker
        if worker is None:
            return
        idx = self._active_connect_index
        try:
            device = self.model.devices[idx] if idx is not None and 0 <= idx < len(self.model.devices) else None
            worker.cancel(current_device=device)
        except Exception:
            pass
        worker.wait(3000)
        self._active_connect_worker = None
        self._active_connect_index = None
        self._connect_timeout_timer.stop()
    
        # 重置仍处于 CONNECTING 状态的协议为连接失败
        if device is not None:
            for protocol in ("ssh", "doip", "someip"):
                if device.get(f"{protocol}_connect_status") == CONNECTING:
                    device[f"{protocol}_connect_status"] = CONNECT_FAILED
                    device[f"{protocol}_connect_info"] = "连接超时，已自动取消"
            self._persist_devices()
            self.on_model_changed()

    def _device_repr(self, index):
        if index is None or index < 0 or index >= len(self.model.devices):
            return "未知设备"
        d = self.model.devices[index]
        return f"设备{index + 1}({d.get('name', '')}) {d.get('doip_ip') or d.get('ip')}:{d.get('doip_port') or d.get('port')}"

    def _on_connect_timeout(self):
        """连接超时看门狗：60秒内未完成连接则自动取消，防止 UI 卡死。"""
        if not self._is_connect_worker_running():
            return

        idx = self._active_connect_index
        device_text = self._device_repr(idx) if idx is not None else "未知设备"
        self.view.append_log(f"连接超时(60s)，自动取消 -> {device_text}")
        MessageToast(self.view).show_toast(f"连接超时，已自动取消 -> {device_text}", 1)
        self._cancel_active_connect_worker()

    def _do_delete(self, index):
        if self._guard_connect_sensitive_action("删除设备", index=index):
            return

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

    def _do_connect(self, index: int, log_signal=None, startup_auto_reconnect=False, reconnect=False, connect_protocol: str | None = None):
        if self._guard_connect_sensitive_action("连接设备", index=index):
            return

        device = self.model.devices[index]
        device["_device_index"] = index
        self._active_connect_index = index

        detail_text = "启动阶段自动重连中，正在建立连接" if startup_auto_reconnect else ("自动重连..." if reconnect else "连接中...")
        device_key = self._device_key(device)
        self._disconnecting_device_keys.discard(device_key)

        if connect_protocol:
            device[f"{connect_protocol}_connect_status"] = CONNECTING
            device[f"{connect_protocol}_connect_info"] = detail_text
            self._persist_devices()
            self.on_model_changed()
        else:
            self._mark_device_connecting(index, detail_text)

        attempt_id = self._next_connect_attempt_id(device)

        if not startup_auto_reconnect and not reconnect:
            prefix = "单协议连接:" + connect_protocol.upper() if connect_protocol else "连接"
            self.view.append_log(f"{prefix} -> {self._device_repr(index)}")
            MessageToast(self.view).show_toast(f"正在{prefix}... 请稍候", 0)

        device_copy = device.copy()
        if connect_protocol:
            device_copy["_connect_protocol"] = connect_protocol
        if startup_auto_reconnect and hasattr(self, '_startup_reconnect_protocols') and self._startup_reconnect_protocols:
            device_copy["_startup_reconnect_protocols"] = self._startup_reconnect_protocols
        device_copy["_device_index"] = index

        worker = ConnectWorker(
            self.device_service,
            device_copy,
            log_signal=log_signal,
            startup_auto_reconnect=startup_auto_reconnect,
            reconnect=reconnect,
            attempt_id=attempt_id
        )

        def on_finished():
            if self._active_connect_worker is worker:
                self._active_connect_worker = None
                self._active_connect_index = None
                self._connect_timeout_timer.stop()

        worker.finished.connect(on_finished)
        self._active_connect_worker = worker
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

        # 启动连接超时看门狗
        self._connect_timeout_timer.start()

        worker.start()

    def _do_edit(self, index: int):
        if self._guard_connect_sensitive_action("编辑设备", index=index):
            return
        device = self.model.devices[index]

        dialog = DeviceEditDialog(device, self.view)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_data = dialog.get_data()
            self.model.update_device(index, **new_data)
            # In case model.update_device doesn't persist properly or blocks 'type', update explicitly if needed
            self._persist_devices()
            self.view.append_log(f"修改设备信息 -> {new_data.get('name')}")
            MessageToast(self.view).show_toast("设备信息修改成功", 1)

    def _on_log_link_clicked(self, url: str):
        if url.startswith("onebox://settings/doip"):
            from app.common.ui.constants import PageConfig
            self.switch_page.emit({}, PageConfig.PAGE_COMMON_CONFIG_DISPLAY)

    def on_close(self):
        """在应用关闭或模块卸载时调用，断开所有设备连接并重置状态/详情。
        调用顺序建议为：
        1. 通过 DeviceService 断开所有底层连接；
        2. 更新模型中每台设备的 *_connect_status 和 *_connect_info 字段；
        3. 持久化到 JSON，确保下次启动时为离线/已断链状态；
        """
        self._connect_timeout_timer.stop()

        for worker in list(self._workers):
            if worker.isRunning():
                worker.cancel()
                worker.wait(1500)

        # 已取消自动重连机制：不再保存 _last_connected_protocols
        # 每次启动软件都需要用户手动连接

        # 重置所有设备的连接状态为已断开
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

    def _device_key(self, device: dict):
        return f"{device.get('ip', '')}:{int(device.get('port', 22))}"

    def _is_connected_like_status(self, status):
        text = str(status or "").strip()
        return ("建链成功" in text) or ("在线" in text)

    def _is_disconnected_like_status(self, status):
        text = str(status or "").strip()
        return text in {OFFLINE, DISCONNECTED, "已断开", "断开", "未连接"}

    def _should_auto_reconnect(self, device: dict) -> bool:
        # 优先使用关闭时保存的已连接协议列表（正常关闭后状态已被重置为断开）
        last_connected = device.get("_last_connected_protocols")
        if last_connected:
            return True
        # 异常退出时状态未被重置，直接检查当前连接状态
        statuses = [
            device.get("ssh_connect_status", OFFLINE),
            device.get("doip_connect_status", OFFLINE),
            device.get("someip_connect_status", OFFLINE),
        ]
        if all(self._is_disconnected_like_status(status) for status in statuses):
            return False
        return any(self._is_connected_like_status(status) for status in statuses)

    def _persist_devices(self):
        """将当前模型中的设备列表落盘到 JSON 配置文件。"""
        self.config_service.save_devices(self.model.to_list())
        event_bus.device_list_changed.emit()
