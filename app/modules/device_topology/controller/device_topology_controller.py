from app.core.base_controller import BaseController
from app.modules.device_topology.model.device_topology_model import TopologyModel
from app.modules.device_topology.view.device_topology_view import TopologyView
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService
from PyQt5 import QtCore


class TopologyController(BaseController):
    def __init__(self, parent=None, device_service: DeviceService = None):
        self.model = TopologyModel(parent)
        self.view = TopologyView(parent)
        super().__init__(self.model, self.view, parent)

        # 注入 DeviceService，并初始化 TopologyService
        # 如果 device_service 为 None，TopologyService 内部会回退到 dummy 模式
        self.device_service = device_service
        # 默认 use_dummy=False，如果 device_service 为空，TopologyService 内部会自动处理
        # 但为了明确意图，如果没注入 device_service，我们也可以显式设为 True
        use_dummy = (device_service is None)
        self.topology_service = TopologyService(device_service=self.device_service, use_dummy=use_dummy)
        self.current_device = None # 存储当前选中的设备信息

        self.view.refresh_btn.clicked.connect(self.refresh)
        # 绑定以太网网络诊断面板的按钮
        self._bind_network_status_buttons()
        self.on_model_changed()

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

    # ---------- 抓包控制（DoIP UDS 路径） ----------
    def _send_eth_mirror_command(self, raw_bytes: bytes, log_label: str) -> None:
        if not self.device_service:
            self.view.append_log(f"[{log_label}] DeviceService 未注入，无法发送指令")
            return
        client = self.device_service.get_doip_client()
        if client is None:
            self.view.append_log(f"[{log_label}] DoIP 未建链，无法发送指令")
            return
        try:
            # 直接发送预组帧 UDS 报文 payload（上层已按需求构造）
            rx = client.send_doip_message(raw_bytes, timeout=2.0)
            self.view.append_log(f"[{log_label}] 指令已发送，响应: {rx.hex() if rx else '无'}")
        except Exception as e:
            self.view.append_log(f"[{log_label}] 发送失败: {e}")

    def _on_capture_ccu_eth(self):
        # 1. 启动 Wireshark 抓包
        self._start_wireshark_capture("CCU ETH数据抓包")

        # 2. 发送 UDS 指令
        # 1003 2701 2702 3101BEE73E （按说明文档：先 1003，再 27 01/02，再 31 01 BE E7 3E 等）
        # 这里简单示例为连续发送，可后续细分为多个 UDS 步骤
        seq = [
            bytes.fromhex("10 03"),          # 诊断会话控制 (示例)
            bytes.fromhex("27 01"),          # 安全访问请求种子
            bytes.fromhex("27 02"),          # 安全访问发送钥匙（示例填充）
            bytes.fromhex("31 01 BE E7 3E"), # 打开 NTL 镜像开关例程
        ]
        for p in seq:
            self._send_eth_mirror_command(p, "CCU ETH数据抓包")

    def _on_capture_node_eth(self):
        # 1. 启动 Wireshark 抓包
        self._start_wireshark_capture("CCU ETH数据抓包")

        # 2. 发送 UDS 指令
        # 1003 2701 2702 3101BEE703
        seq = [
            bytes.fromhex("10 03"),
            bytes.fromhex("27 01"),
            bytes.fromhex("27 02"),
            bytes.fromhex("31 01 BE E7 03"),
        ]
        for p in seq:
            self._send_eth_mirror_command(p, "IDC/ADC/IFC/TBOX/FL ETH数据抓包")

    def _on_capture_vehicle_eth(self):
        # 1. 启动 Wireshark 抓包
        self._start_wireshark_capture("CCU ETH数据抓包")

        # 2. 发送 UDS 指令
        # 1003 2701 2702 3101BEE7FF
        seq = [
            bytes.fromhex("10 03"),
            bytes.fromhex("27 01"),
            bytes.fromhex("27 02"),
            bytes.fromhex("31 01 BE E7 FF"),
        ]
        for p in seq:
            self._send_eth_mirror_command(p, "整车 ETH数据抓包")

    def _start_wireshark_capture(self, log_label: str) -> None:
        """尝试启动 Wireshark 并开始抓包"""
        import subprocess
        import os

        # 1. 检查 Wireshark 是否已运行
        try:
            # 配置 startupinfo 以隐藏控制台窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # 使用 tasklist 检查进程
            output_bytes = subprocess.check_output(
                ['tasklist', '/FI', 'IMAGENAME eq Wireshark.exe'],
                startupinfo=startupinfo
            )
            output = output_bytes.decode('gbk', errors='ignore')

            if "Wireshark.exe" in output:
                self.view.append_log(f"[{log_label}] Wireshark 已在运行，跳过启动")
                return
        except Exception:
            # 检查失败则忽略，继续尝试启动
            pass

        # 2. 尝试从注册表获取 Wireshark 路径，或者使用默认路径
        wireshark_path = r"C:\Program Files\Wireshark\Wireshark.exe"
        if not os.path.exists(wireshark_path):
            # 简单的回退尝试
            wireshark_path = "wireshark"

        try:
            # -k: 立即开始抓包
            # -i <interface>: 指定接口，如果不指定通常会使用默认或上次使用的接口，或者弹出选择框
            # 这里仅启动 Wireshark 并立即开始抓包（使用默认接口或首选接口）
            # 如果需要指定接口，需要知道接口名称或索引，例如 -i 1
            subprocess.Popen([wireshark_path, "-k"])
            self.view.append_log(f"[{log_label}] 已尝试启动 Wireshark 抓包")
        except Exception as e:
            self.view.append_log(f"[{log_label}] 启动 Wireshark 失败: {e}")

    # ---------- 故障读取（DTC 0x19 02 2F） ----------
    def _read_dtc_and_match(self, panel_key: str, codes: dict, empty_text: str):
        panel = self.view.network_status_panel
        if not self.device_service:
            self.view.append_log("DeviceService 未注入，无法读取 DTC")
            panel.set_status(panel_key, "服务不可用")
            return
        client = self.device_service.get_doip_client()
        if client is None:
            self.view.append_log("DoIP 未建链，无法读取 DTC")
            panel.set_status(panel_key, "DoIP 未连接")
            return
        try:
            req = bytes.fromhex("19 02 2F")
            rx = client.send_doip_message(req, timeout=2.0)
            if not rx:
                panel.set_status(panel_key, empty_text)
                return
            # 简单 hex 查找匹配 DTC 码
            hex_str = rx.hex().upper()
            hits = [name for code, name in codes.items() if code in hex_str]
            if hits:
                panel.set_status(panel_key, ", ".join(hits))
            else:
                panel.set_status(panel_key, empty_text)
        except Exception as e:
            self.view.append_log(f"读取 DTC 失败: {e}")
            panel.set_status(panel_key, "读取失败")

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
        if not self.device_service or not self.current_device:
            panel.set_status("tx_rx_stats", "无设备信息或服务不可用")
            return
        cmd = "Use -mib -all"  # 按文档 demo
        out, err, code = self.device_service.execute_ssh_command_on_device(self.current_device, cmd)
        if code == 0:
            panel.set_status("tx_rx_stats", out.strip().splitlines()[0] if out else "OK")
        else:
            panel.set_status("tx_rx_stats", f"执行失败: {err or code}")

    # ---------- Ping 系列（SSH ping 两个 VLAN IP） ----------
    def _ping_pair(self, name: str, ip0: str, ip4: str, panel_key: str):
        panel = self.view.network_status_panel
        if not self.device_service or not self.current_device:
            panel.set_status(panel_key, "无设备信息或服务不可用")
            return
        def _run_ping(ip: str) -> bool:
            cmd = f"ping -c 2 {ip}"  # Linux 上的 ping，后续可根据实际环境调整
            out, err, code = self.device_service.execute_ssh_command_on_device(self.current_device, cmd, timeout=10)
            return code == 0

        ok0 = _run_ping(ip0)
        ok4 = _run_ping(ip4)
        text0 = "ping VLAN0 OK" if ok0 else "ping VLAN0 NG"
        text4 = "ping VLAN4 OK" if ok4 else "ping VLAN4 NG"
        panel.set_status(panel_key, f"{text0}, {text4}")
        self.view.append_log(f"[{name}] {text0}, {text4}")

    def _on_ping_node(self, key: str):
        mapping = {
            "idc": ("IDC", "172.16.0.43", "172.16.64.43"),
            "adc": ("ADC", "172.16.0.14", "172.16.64.14"),
            "tbox": ("TBOX", "172.16.0.45", "172.16.64.45"),
            "fl": ("FL", "172.16.0.21", "172.16.64.21"),
            # IFC/RT1/RT2 暂未提供具体 IP，后续可补充
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
        # 调用 TopologyService 获取快照
        try:
            # 传入当前设备信息用于 SSH 连接
            snapshot = self.topology_service.fetch_snapshot(device_info=self.current_device)
            # 将 snapshot 数据更新到 model
            # 这里假设 model 有 update_from_snapshot 方法，或者手动更新字段
            # self.model.update_from_snapshot(snapshot)
            # 暂时手动更新 model 字段以匹配现有逻辑
            self.model.nodes = snapshot.nodes
            self.model.networks = snapshot.networks
            # 触发界面更新
            self.on_model_changed()

            # 更新信息块
            self.view.update_vehicle_info(snapshot.vehicle_info)
            self.view.update_service_status_info(snapshot.service_status)
            self.view.update_security_info(snapshot.security_info)
            self.view.update_network_mgmt(snapshot.network_management)
            self.view.update_storage_info(snapshot.storage_info)
            self.view.append_log("已刷新拓扑信息")
        except Exception as e:
            self.view.append_log(f"刷新拓扑失败: {e}")


    def get_view(self):
        return self.view
