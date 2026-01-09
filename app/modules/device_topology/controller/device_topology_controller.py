from app.core.base_controller import BaseController
from app.modules.device_topology.model.device_topology_model import TopologyModel
from app.modules.device_topology.view.device_topology_view import TopologyView
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService
from app.common.utils.worker import Worker


class TopologyController(BaseController):
    def __init__(self, parent=None, device_service: DeviceService = None):
        self.model = TopologyModel(parent)
        self.view = TopologyView(parent)
        super().__init__(self.model, self.view, parent)
        self._workers = []  # 存储 worker 防止被回收
        # 注入 DeviceService，并初始化 TopologyService
        # 如果 device_service 为 None，TopologyService 内部会回退到 dummy 模式
        self.device_service = device_service
        # 但为了明确意图，如果没注入 device_service，我们也可以显式设为 True
        self.topology_service = TopologyService(device_service=self.device_service)
        self.current_device = None # 存储当前选中的设备信息

        self.view.refresh_btn.clicked.connect(self.refresh)

        # 绑定拓扑图工具栏的请求信号
        if hasattr(self.view.topology_widget, 'request_info_update'):
            self.view.topology_widget.request_info_update.connect(self._on_info_update_requested)

        # 绑定以太网网络诊断面板的按钮
        self._bind_network_status_buttons()
        self.on_model_changed()

    def _on_info_update_requested(self, info_type: str):
        """处理信息更新请求"""
        # self.view.append_log(f"请求更新: {info_type}")

        def task(log_callback):
            try:
                if info_type == "车辆信息":
                    return "vehicle_info", self.topology_service.fetch_vehicle_info(log_callback)
                elif info_type == "服务状态信息":
                    return "service_status", self.topology_service.fetch_service_status(log_callback)
                elif info_type == "证书信息":
                    return "security_info", self.topology_service.fetch_security_info(log_callback)
                elif info_type == "网络管理":
                    return "network_mgmt", self.topology_service.fetch_network_mgmt(log_callback)
                elif info_type == "储存信息":
                    return "storage_info", self.topology_service.fetch_storage_info(log_callback=log_callback)
                elif info_type == "版本信息":
                    return "version_info", self.topology_service.fetch_version_info(log_callback=log_callback)
                return None, None
            except Exception as e:
                log_callback(f"{info_type} 更新失败: {e}")
                return None, None

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result):
            if not result:
                return

            type_key, info = result
            if not info:
                return

            if type_key == "vehicle_info":
                self.view.update_vehicle_info(info)
            elif type_key == "service_status":
                self.view.update_service_status_info(info)
            elif type_key == "security_info":
                self.view.update_security_info(info)
            elif type_key == "network_mgmt":
                self.view.update_network_mgmt(info)
            elif type_key == "storage_info":
                self.view.update_storage_info(info)
            elif type_key == "version_info":
                self.view.update_version_info(info)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()

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
        for key in ("adc", "idc", "tbox", "fl", "ifc", "rt1", "rt2"):
            btn = panel.button(f"ping_{key}")
            if btn:
                btn.clicked.connect(lambda _, k=key: self._on_ping_node(k))


    def _on_capture_ccu_eth(self):
        """
        CCU ETH数据抓包:
        1. 检查 Wireshark 是否运行，若未运行则启动
        2. 发送 DoIP 激活指令 (10 03, 27 01/02, 31 01 BE E7 3E)
        """
        def log_callback(msg: str):
            self.view.append_log(msg)

        success = self.topology_service.capture_ccu_eth(log_callback)
        if success:
            self.view.append_log("CCU ETH 数据抓包指令发送完成")
        else:
            self.view.append_log("CCU ETH 数据抓包指令发送失败")

    def _on_capture_node_eth(self):
        # 发送 UDS 指令
        # 1003 2701 2702 3101BEE703
        def log_callback(msg: str):
            self.view.append_log(msg)

        success = self.topology_service.capture_node_eth(log_callback)
        if success:
            self.view.append_log("IDC/ADC/IFC/TBOX/FL ETH数据抓包完成")
        else:
            self.view.append_log("IDC/ADC/IFC/TBOX/FL ETH数据抓包失败")

    def _on_capture_vehicle_eth(self):
        #  发送 UDS 指令
        # 1003 2701 2702 3101BEE7FF
        def task(log_callback):
            return self.topology_service.capture_vehicle_eth(log_callback)

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(success):
            if success:
                self.view.append_log("整车 ETH数据抓包指令发送完成")
            else:
                self.view.append_log("整车 ETH数据抓包指令发送失败")
            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()


    # ---------- 故障读取（DTC 0x19 02 2F） ----------
    def _read_dtc_and_match(self, panel_key: str, codes: dict, empty_text: str):
        panel = self.view.network_status_panel
        if not self.device_service:
            self.view.append_log("DeviceService 未注入，无法读取 DTC")
            panel.set_status(panel_key, "服务不可用")
            return

        def task(log_callback):
            client = self.device_service.get_doip_client()
            if client is None:
                log_callback("DoIP 未建链，无法读取 DTC")
                return "DoIP 未连接"
            try:
                req = bytes.fromhex("19 02 2F")
                log_callback(f"发送 DTC 读取指令: {req.hex(' ').upper()}")
                rx = client.send_doip_message(req, timeout=2.0)
                if not rx:
                    log_callback("DTC 读取无响应")
                    return empty_text

                log_callback(f"收到 DTC 响应: {rx.hex(' ').upper()}")
                # 简单 hex 查找匹配 DTC 码
                hex_str = rx.hex().upper()
                hits = [name for code, name in codes.items() if code in hex_str]
                if hits:
                    return ", ".join(hits)
                else:
                    return empty_text
            except Exception as e:
                log_callback(f"读取 DTC 失败: {e}")
                return "读取失败"

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result):
            panel.set_status(panel_key, result)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def _on_read_switch_fault(self):
        codes = {
            "B140716": "Ethernet switch 欠压故障",
            "B14074B": "Ethernet switch 过温故障",
        }
        self._read_dtc_and_match("switch_status", codes, "无switch DTC")

    def _on_read_pfe_fault(self):
        codes = {
            "B1F0794": "PFE软件故障",
            "B1F0796": "PFE硬件故障",
        }
        self._read_dtc_and_match("pfe_status", codes, "无PFE DTC")

    # ---------- TX/RX 计数（SSH demo 命令） ----------
    def _on_tx_rx_count(self):
        panel = self.view.network_status_panel
        self.view.append_log("正在获取 TX/RX 计数...")

        def task(log_callback):
            return self.topology_service.get_tx_rx_count(log_callback=log_callback)

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result_tuple):
            success, result = result_tuple
            if success:
                self.view.append_log(f"获取 TX/RX 计数成功: {result}")
            else:
                self.view.append_log(f"获取 TX/RX 计数失败: {result}")
            panel.set_status("tx_rx_stats", result)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    # ---------- Ping 系列（SSH ping 两个 VLAN IP） ----------
    def _ping_pair(self, name: str, ip0: str, ip4: str, panel_key: str):
        panel = self.view.network_status_panel

        def task(log_callback):
            # Ping VLAN0
            log_callback(f"正在 Ping {name} (VLAN0: {ip0})...")
            ok0 = self.topology_service.ping_ip(ip0, log_callback=log_callback)
            log_callback(f"Ping {name} (VLAN0: {ip0}) 结果: {'成功' if ok0 else '失败'}")

            # Ping VLAN4
            log_callback(f"正在 Ping {name} (VLAN4: {ip4})...")
            ok4 = self.topology_service.ping_ip(ip4, log_callback=log_callback)
            log_callback(f"Ping {name} (VLAN4: {ip4}) 结果: {'成功' if ok4 else '失败'}")

            return ok0, ok4

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result):
            ok0, ok4 = result
            text0 = "ping VLAN0 OK" if ok0 else "ping VLAN0 NG"
            text4 = "ping VLAN4 OK" if ok4 else "ping VLAN4 NG"
            panel.set_status(panel_key, f"{text0}, {text4}")
            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def _on_ping_node(self, key: str):
        mapping = {
            "idc": ("IDC", "172.16.0.43", "172.16.64.43"),
            "adc": ("ADC", "172.16.0.14", "172.16.64.14"),
            "tbox": ("TBOX", "172.16.0.45", "172.16.64.45"),
            "fl": ("FL", "172.16.0.21", "172.16.64.21"),
            "rt1": ("RT1", "172.16.0.79", "172.16.64.79"),
            "rt2": ("RT2", "172.16.1.79")
        }
        if key not in mapping:
            self.view.append_log(f"[Ping] 未配置节点: {key}")
            return
        name, ip0, ip4 = mapping[key]
        self._ping_pair(name, ip0, ip4, f"ping_{key}_result")

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

        def task(log_callback):
            try:
                # 传入 log_callback 以捕获详细日志
                return self.topology_service.fetch_snapshot(log_callback=log_callback)
            except Exception as e:
                log_callback(f"刷新失败: {e}")
                import traceback
                traceback.print_exc()
                return None

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(snapshot):
            self.view.set_loading(False)
            if snapshot:
                # 将 snapshot 数据更新到 model
                self.model.nodes = snapshot.nodes
                # 触发界面更新
                self.on_model_changed()

                # 强制更新拓扑图节点
                if hasattr(self.view, 'topology_widget'):
                    self.view.topology_widget.init_nodes(snapshot.nodes)

                # 更新其他面板信息 (根据用户需求暂时注释掉，只更新拓扑图)
                # self.view.update_vehicle_info(snapshot.vehicle_info)
                # self.view.update_service_status_info(snapshot.service_status)
                # self.view.update_security_info(snapshot.security_info)
                # self.view.update_network_mgmt(snapshot.network_management)
                # self.view.update_storage_info(snapshot.storage_info)

                self.view.append_log("以太网拓扑刷新完成")
            else:
                self.view.append_log("以太网拓扑刷新失败或无数据")

            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def _refresh_can_lin_topology(self):
        """刷新 CAN/LIN 拓扑"""
        self.view.set_loading(True)
        self.view.append_log("正在刷新 CAN/LIN 拓扑数据...")

        def task(log_callback):
            try:
                # 调用 TopologyService 中的 fetch_can_lin_snapshot
                return self.topology_service.fetch_can_lin_snapshot(log_callback=log_callback)
            except Exception as e:
                log_callback(f"CAN/LIN 刷新失败: {e}")
                import traceback
                traceback.print_exc()
                return None

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result):
            self.view.set_loading(False)
            if result:
                self.view.append_log("CAN/LIN 拓扑刷新完成")
                # 更新拓扑图节点
                if hasattr(self.view, 'graphics_can_lin') and hasattr(self.view.graphics_can_lin, 'topology'):
                    self.view.graphics_can_lin.topology.init_nodes(result)
            else:
                self.view.append_log("CAN/LIN 拓扑刷新失败或无数据")

            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def get_view(self):
        return self.view
