import logging

from app.core.base_controller import BaseController
from app.modules.device_topology.model.device_topology_model import TopologyModel
from app.modules.device_topology.view.device_topology_view import TopologyView
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService
from app.common.utils.worker import Worker

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TopologyController(BaseController):
    def __init__(self, parent=None, device_service: DeviceService = None):
        self.model = TopologyModel(parent)
        self.view = TopologyView(parent)
        super().__init__(self.model, self.view, parent)
        # 注入 DeviceService，并初始化 TopologyService
        # 如果 device_service 为 None，TopologyService 内部会回退到 dummy 模式
        self.device_service = device_service
        # 但为了明确意图，如果没注入 device_service，我们也可以显式设为 True
        self.topology_service = TopologyService(device_service=self.device_service)
        self._connect_service_signals()
        self.current_device = None # 存储当前选中的设备信息

        self.view.refresh_btn.clicked.connect(self.refresh)

        # 绑定拓扑图工具栏的请求信号
        if hasattr(self.view.topology_widget, 'request_info_update'):
            self.view.topology_widget.request_info_update.connect(self._on_info_update_requested)

        # 绑定以太网网络诊断面板的按钮
        self._bind_network_status_buttons()
        self.on_model_changed()

        # 实时监控定时器
        # self.monitor_timer = QTimer(self)
        # self.monitor_timer.setInterval(3000) # 3秒轮询
        # self.monitor_timer.timeout.connect(self._on_poll_timer)
        # self.monitor_timer.start()

    def _connect_service_signals(self):
        """连接 Service 信号"""
        # 1. 车辆信息
        self.topology_service.sig_vin_updated.connect(lambda val: self.view.update_single_vehicle_info("vin", val))
        self.topology_service.sig_vehicle_mode_updated.connect(lambda val: self.view.update_single_vehicle_info("vehicle_mode", val))
        self.topology_service.sig_user_mode_updated.connect(lambda val: self.view.update_single_vehicle_info("user_mode", val))
        self.topology_service.sig_factory_mode_updated.connect(lambda val: self.view.update_single_vehicle_info("factory_mode", val))
        self.topology_service.sig_voltage_updated.connect(lambda val: self.view.update_single_vehicle_info("voltage", val))

        # 2. 证书/安全信息
        self.topology_service.sig_cert_infos_updated.connect(lambda val: self.view.update_single_security_info("cert_info", val))
        self.topology_service.sig_key_slot_status_updated.connect(lambda val: self.view.update_single_security_info("key_slot_status", val))
        self.topology_service.sig_cms_env_updated.connect(lambda val: self.view.update_single_security_info("cms_env", val))

        # 3. 存储/版本/服务
        self.topology_service.sig_storage_updated.connect(lambda val: self.view.update_single_storage_info("a_core_storage", val))
        self.topology_service.sig_version_updated.connect(lambda val: self.view.update_single_version_info("m_core_storage", val))
        self.topology_service.sig_service_summary_updated.connect(lambda val: self.view.update_single_service_status("status_summary", val))

        # 4. 网络管理
        self.topology_service.sig_power_wake_updated.connect(lambda val: self.view.update_single_network_info("power_wake_source", val))
        self.topology_service.sig_pnc_updated.connect(lambda val: self.view.update_single_network_info("pnc", val))
        self.topology_service.sig_rt1_net_updated.connect(lambda val: self.view.update_single_network_info("rt1_net", val))

        # 5. 其他
        self.topology_service.sig_topology_updated.connect(self._on_topology_updated)
        self.topology_service.sig_can_lin_topology_updated.connect(self._on_can_lin_topology_updated)
        self.topology_service.sig_switch_fault_updated.connect(lambda res: self.view.network_status_panel.set_status("switch_status", res))
        self.topology_service.sig_pfe_fault_updated.connect(lambda res: self.view.network_status_panel.set_status("pfe_status", res))
        self.topology_service.sig_tx_rx_updated.connect(self._on_tx_rx_updated)
        self.topology_service.sig_capture_finished.connect(self._on_capture_finished)
        self.topology_service.sig_ping_result.connect(self._on_ping_result)
        self.topology_service.log_signal.connect(self._update_log)
        self.topology_service.sig_error.connect(self._on_service_error)


    def _update_log(self, message: str):
        self.view.append_log(message)
        logger.info(message)

    def _on_service_error(self, message: str):
        """处理 Service 返回的错误"""
        self.view.set_loading(False)
        self.view.append_log(f"操作失败: {message}")
        logger.error(message)

    def _on_tx_rx_updated(self, result_tuple):
        success, result = result_tuple
        if success:
            self.view.append_log(f"获取 TX/RX 计数成功: {result}")
        else:
            self.view.append_log(f"获取 TX/RX 计数失败: {result}")
        self.view.network_status_panel.set_status("tx_rx_stats", result)

    def _on_capture_finished(self, success, msg):
        self.view.append_log(msg)

    def _on_ping_result(self, key, result):
        # 结果映射到对应的UI元素
        # key 是我们调用时传入的，比如 "adc"
        panel_key = f"ping_{key}_result"
        ok0, ok4 = result

        text0 = "ping VLAN0 OK" if ok0 else "ping VLAN0 NG"

        if ok4 is None:
            # 只有 VLAN0 的情况
            status_text = text0
        else:
            text4 = "ping VLAN4 OK" if ok4 else "ping VLAN4 NG"
            status_text = f"{text0}, {text4}"

        if hasattr(self.view, 'network_status_panel'):
            self.view.network_status_panel.set_status(panel_key, status_text)

        self._update_log(f"Ping {key.upper()} 完成: {status_text}")

    def _on_topology_updated(self, snapshot):
        """处理以太网拓扑更新信号"""
        self.view.set_loading(False)
        if snapshot:
            # 将 snapshot 数据更新到 model
            self.model.nodes = snapshot.nodes
            # 触发界面更新
            self.on_model_changed()

            # 强制更新拓扑图节点
            if hasattr(self.view, 'topology_widget'):
                self.view.topology_widget.init_nodes(snapshot.nodes)

            self.view.append_log("以太网拓扑刷新完成")
        else:
            self.view.append_log("以太网拓扑刷新失败或无数据")

    def _on_can_lin_topology_updated(self, result):
        """处理 CAN/LIN 拓扑更新信号"""
        self.view.set_loading(False)
        if result:
            self.view.append_log("CAN/LIN 拓扑刷新完成")
            # 更新拓扑图节点
            if hasattr(self.view, 'graphics_can_lin') and hasattr(self.view.graphics_can_lin, 'topology'):
                self.view.graphics_can_lin.topology.init_nodes(result)
        else:
            self.view.append_log("CAN/LIN 拓扑刷新失败或无数据")

    def _on_info_update_requested(self, info_type: str):
        """处理信息更新请求"""
        # self.view.append_log(f"请求更新: {info_type}")
        if info_type == "车辆信息":
            # 在重新请求前，清理旧的显示（可选），但根据需求，用户希望"重新请求"
            # Service层已经处理了状态重置（发送"请求中..."）
            self.topology_service.request_vehicle_info()
        elif info_type == "服务状态信息":
            self.topology_service.request_service_status()
        elif info_type == "证书信息":
            self.topology_service.request_security_info()
        elif info_type == "网络管理":
            self.topology_service.request_network_mgmt()
        elif info_type == "储存信息":
            self.topology_service.request_storage_info()
        elif info_type == "版本信息":
            self.topology_service.request_version_info()

    def _bind_network_status_buttons(self) -> None:
        panel = getattr(self.view, "network_status_panel", None)
        if panel is None:
            return
        # 抓包相关
        if panel.button("capture_ccu_eth"):
            panel.button("capture_ccu_eth").clicked.connect(self._on_capture_ccu_eth)
        if panel.button("capture_node_eth"):
            panel.button("capture_node_eth").clicked.connect(self._on_capture_node_eth)
        if panel.button("capture_vehicle_eth"):
            panel.button("capture_vehicle_eth").clicked.connect(self._on_capture_vehicle_eth)

        # 故障读取
        if panel.button("read_switch_fault"):
            panel.button("read_switch_fault").clicked.connect(self._on_read_switch_fault)
        if panel.button("read_ntl_fault"):
            panel.button("read_ntl_fault").clicked.connect(self._on_read_pfe_fault)

        # TX/RX 计数
        if panel.button("tx_rx_data_count"):
            panel.button("tx_rx_data_count").clicked.connect(self._on_tx_rx_count)

        # Ping 按钮
        for key in ("idc", "adc_soc", "adc_mcu", "tbox", "fl", "rt1", "rt2"):
            btn = panel.button(f"ping_{key}")
            if btn:
                btn.clicked.connect(lambda _, k=key: self._on_ping_node(k))

    def _run_async_worker(self, target_func):
        """通用异步任务执行器，用于执行耗时的Service操作"""
        if not hasattr(self, '_workers'):
            self._workers = []

        worker = Worker(target_func)
        worker.log_signal.connect(self._update_log)

        def on_finished():
            if hasattr(self, '_workers') and worker in self._workers:
                self._workers.remove(worker)

        worker.finished.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def _run_capture_task(self, target_func, task_name: str):
        """
        执行抓包任务的专用封装
        - 确保任务互斥（避免重复或冲突调用）
        - 统一日志输出
        """
        if getattr(self, '_is_capturing', False):
            self._update_log(f"当前已有抓包任务正在进行，请稍候再试...")
            return

        self._is_capturing = True
        self._update_log(f"开始执行: {task_name}")

        def wrapped_task():
            try:
                target_func()
            finally:
                pass # 这里不便重置标志位，因为 Worker 是异步的

        # 注意：这里的 target_func 是在 Worker 线程中执行的
        # 标志位的重置需要在主线程的回调中进行，无论成功与否

        if not hasattr(self, '_workers'):
            self._workers = []

        worker = Worker(wrapped_task)
        worker.log_signal.connect(self._update_log)

        def on_finished():
            self._is_capturing = False
            self._update_log(f"{task_name} 执行结束")
            if hasattr(self, '_workers') and worker in self._workers:
                self._workers.remove(worker)

        worker.finished.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def _on_capture_ccu_eth(self):
        """CCU ETH数据抓包: 发送 DoIP 激活指令"""
        self._run_capture_task(self.topology_service.request_capture_ccu_eth, "CCU ETH数据抓包")

    def _on_capture_node_eth(self):
        """节点 ETH数据抓包"""
        self._run_capture_task(self.topology_service.request_capture_node_eth, "节点 ETH数据抓包")

    def _on_capture_vehicle_eth(self):
        """整车 ETH数据抓包"""
        self._run_capture_task(self.topology_service.request_capture_vehicle_eth, "整车 ETH数据抓包")

    def _on_poll_timer(self):
        """定时轮询更新"""
        # 仅当当前标签页为以太网拓扑时才轮询
        if self.view.tab_widget.currentIndex() == 0:
            self.topology_service.request_eth_snapshot()
        # 后续可添加 CAN/LIN 的轮询，如果性能允许

    # ---------- 故障读取（DTC 0x19 02 2F） ----------
    def _on_read_switch_fault(self):
        self.topology_service.request_switch_fault()

    def _on_read_pfe_fault(self):
        self.topology_service.request_pfe_fault()

    # ---------- TX/RX 计数（SSH demo 命令） ----------
    def _on_tx_rx_count(self):
        panel = self.view.network_status_panel
        self._update_log("正在获取 TX/RX 计数...")
        self.topology_service.request_tx_rx_count()

    # ---------- Ping 系列（SSH ping 两个 VLAN IP） ----------
    def _on_ping_node(self, key: str):
        # 逻辑已移至 TopologyService，直接调用请求方法
        self.topology_service.request_ping_node(key)

    def handle_switch_payload(self, payload: dict):
        """处理页面切换时传递的 payload，例如设备信息"""
        if payload and "device" in payload:
            self.current_device = payload["device"]
            self.view.append_log(f"已切换到设备: {self.current_device.get('ip')}")
            # 自动刷新或等待用户点击刷新
            # self.refresh()

    def refresh(self):
        """刷新拓扑数据"""
        current_index = self.view.tab_widget.currentIndex()
        if current_index == 0:
            self._refresh_ethernet_topology()
        elif current_index == 1:
            self._refresh_can_lin_topology()
        else:
            self.view.append_log("未知标签页，无法刷新")

    def _refresh_ethernet_topology(self):
        """刷新以太网拓扑"""
        self.view.set_loading(True)
        self.view.append_log("正在刷新以太网拓扑数据...")
        self.topology_service.request_eth_snapshot()

    def _refresh_can_lin_topology(self):
        """刷新 CAN/LIN 拓扑"""
        self.view.set_loading(True)
        self.view.append_log("正在刷新 CAN/LIN 拓扑数据...")
        self.topology_service.request_can_lin_snapshot()

    def get_view(self):
        return self.view
