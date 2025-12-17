# python
from PyQt5 import QtWidgets, QtGui, QtCore

from app.common.ui.widgets import ModernButton
from app.modules.device_topology.view.network_status import NetworkStatusPanel
from app.modules.device_topology.view.topology_widget import SimpleTopologyWindow
from app.presentation.views.base_view import BaseView


class TopologyView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(2)

        topo_group = QtWidgets.QGroupBox("车辆拓扑图")
        topo_layout = QtWidgets.QVBoxLayout()

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.refresh_btn = ModernButton("刷新拓扑", "#0EA5E9", "🔄")
        btn_layout.addWidget(self.refresh_btn)
        topo_layout.addLayout(btn_layout)

        self.graphics = SimpleTopologyWindow()
        topo_layout.addWidget(self.graphics)
        topo_group.setLayout(topo_layout)

        network_panel = QtWidgets.QGroupBox("网络状态")
        network_layout = QtWidgets.QVBoxLayout()
        self.network_grid = QtWidgets.QGridLayout()
        network_layout.addLayout(self.network_grid)
        network_layout.addStretch()
        network_panel.setLayout(network_layout)

        splitter.addWidget(topo_group)
        # 新增以太网网络诊断分组
        eth_diag_group = QtWidgets.QGroupBox("以太网网络诊断")
        eth_diag_layout = QtWidgets.QVBoxLayout()
        eth_diag_layout.setContentsMargins(8, 8, 8, 8)
        eth_diag_layout.setSpacing(8)
        # 挂成成员，便于 controller 访问
        self.network_status_panel = NetworkStatusPanel()
        eth_diag_layout.addWidget(self.network_status_panel)
        eth_diag_group.setLayout(eth_diag_layout)
        splitter.addWidget(eth_diag_group)
        splitter.setSizes([650, 350])
        layout.addWidget(splitter, 3)

        # 信息块（替换原 Tab）
        self._init_info_blocks(layout)

        # 操作日志区与设备管理界面保持一致
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(130)
        self.log_view.setPlaceholderText("这里显示拓扑相关的操作日志...")
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, 2)

    def _init_info_blocks(self, parent_layout: QtWidgets.QVBoxLayout):
        container = QtWidgets.QWidget()
        container.setMaximumHeight(220)
        blocks_layout = QtWidgets.QHBoxLayout(container)
        blocks_layout.setSpacing(12)
        blocks_layout.setContentsMargins(0, 0, 0, 0)

        # 车辆信息
        self.vehicle_group = QtWidgets.QGroupBox("车辆信息")
        v_layout = QtWidgets.QFormLayout()
        self.vehicle_labels = {
            "vin": QtWidgets.QLabel("—"),
            "vehicle_mode": QtWidgets.QLabel("—"),
            "user_mode": QtWidgets.QLabel("—"),
            "factory_mode": QtWidgets.QLabel("—"),
            "voltage": QtWidgets.QLabel("—")
        }
        v_layout.addRow("VIN码：", self.vehicle_labels["vin"])
        v_layout.addRow("车辆模式：", self.vehicle_labels["vehicle_mode"])
        v_layout.addRow("用户模式：", self.vehicle_labels["user_mode"])
        v_layout.addRow("工厂模式：", self.vehicle_labels["factory_mode"])
        v_layout.addRow("电压值：", self.vehicle_labels["voltage"])
        self.vehicle_group.setLayout(v_layout)
        self.vehicle_group.setMinimumHeight(120)
        blocks_layout.addWidget(self.vehicle_group)

        # 服务状态信息
        self.status_group = QtWidgets.QGroupBox("服务状态信息")
        s_layout = QtWidgets.QFormLayout()
        self.status_labels = {
            "srv_id01": QtWidgets.QLabel("—"),
            "srv_id02": QtWidgets.QLabel("—"),
            "srv_id03": QtWidgets.QLabel("—")
        }
        s_layout.addRow("SrvID01：", self.status_labels["srv_id01"])
        s_layout.addRow("SrvID02：", self.status_labels["srv_id02"])
        s_layout.addRow("SrvID03：", self.status_labels["srv_id03"])
        self.status_group.setLayout(s_layout)
        self.status_group.setMinimumHeight(80)
        blocks_layout.addWidget(self.status_group)

        # 证书信息
        self.security_group = QtWidgets.QGroupBox("证书信息")
        sec_layout = QtWidgets.QFormLayout()
        self.sec_labels = {
            "cert_server": QtWidgets.QLabel("—"),
            "pki_status": QtWidgets.QLabel("—"),
            "cert_valid_date": QtWidgets.QLabel("—"),
            "key_slot_status": QtWidgets.QLabel("—"),
            "tls_switch": QtWidgets.QLabel("—"),
            "secoc_switch": QtWidgets.QLabel("—"),
            "cms_env": QtWidgets.QLabel("—")
        }
        sec_layout.addRow("证书服务器：", self.sec_labels["cert_server"])
        sec_layout.addRow("PKI服务状态：", self.sec_labels["pki_status"])
        sec_layout.addRow("证书有效日期：", self.sec_labels["cert_valid_date"])
        sec_layout.addRow("密钥槽状态：", self.sec_labels["key_slot_status"])
        sec_layout.addRow("TLS开关状态：", self.sec_labels["tls_switch"])
        sec_layout.addRow("SecOC开关状态：", self.sec_labels["secoc_switch"])
        sec_layout.addRow("CMS环境：", self.sec_labels["cms_env"])
        self.security_group.setLayout(sec_layout)
        self.security_group.setMinimumHeight(220)
        blocks_layout.addWidget(self.security_group)

        # 网络管理
        self.net_group = QtWidgets.QGroupBox("网络管理")
        net_layout = QtWidgets.QFormLayout()
        self.net_labels = {
            "power_wake_source": QtWidgets.QLabel("—"),
            "pnc": QtWidgets.QLabel("—"),
            "rt1_net_source": QtWidgets.QLabel("—"),
            "rt2_net_source": QtWidgets.QLabel("—"),
            "rt1_ext_msg": QtWidgets.QLabel("—"),
            "rt2_ext_msg": QtWidgets.QLabel("—"),
            "a_core_net_req": QtWidgets.QLabel("—"),
            "obd_can_net": QtWidgets.QLabel("—")
        }
        net_layout.addRow("电源唤醒源：", self.net_labels["power_wake_source"])
        net_layout.addRow("PNC：", self.net_labels["pnc"])
        net_layout.addRow("RT1网络维持源：", self.net_labels["rt1_net_source"])
        net_layout.addRow("RT2网络维持源：", self.net_labels["rt2_net_source"])
        net_layout.addRow("RT1外网报文情况：", self.net_labels["rt1_ext_msg"])
        net_layout.addRow("RT2外网报文情况：", self.net_labels["rt2_ext_msg"])
        net_layout.addRow("A核应用网络请求：", self.net_labels["a_core_net_req"])
        net_layout.addRow("OBD_CAN网络情况：", self.net_labels["obd_can_net"])
        self.net_group.setLayout(net_layout)
        self.net_group.setMinimumHeight(220)
        blocks_layout.addWidget(self.net_group)

        # 存储信息
        self.storage_group = QtWidgets.QGroupBox("存储信息")
        st_layout = QtWidgets.QFormLayout()
        self.storage_labels = {
            "a_core_storage": QtWidgets.QLabel("—"),
            "m_core_storage": QtWidgets.QLabel("—")
        }
        st_layout.addRow("A核存储情况：", self.storage_labels["a_core_storage"])
        st_layout.addRow("M核存储情况：", self.storage_labels["m_core_storage"])
        self.storage_group.setLayout(st_layout)
        self.storage_group.setMinimumHeight(50)
        blocks_layout.addWidget(self.storage_group)

        # 平均分布
        for i in range(blocks_layout.count()):
            blocks_layout.setStretch(i, 1)
        parent_layout.addWidget(container)

    def update_vehicle_info(self, info: dict):
        self.vehicle_labels["vin"].setText(info.get("vin", "—"))
        self.vehicle_labels["vehicle_mode"].setText(info.get("vehicle_mode", "—"))
        self.vehicle_labels["user_mode"].setText(info.get("user_mode", "—"))
        self.vehicle_labels["factory_mode"].setText(info.get("factory_mode", "—"))
        self.vehicle_labels["voltage"].setText(info.get("voltage", "—"))

    def update_service_status_info(self, info: dict):
        self.status_labels["srv_id01"].setText(info.get("srv_id01", "—"))
        self.status_labels["srv_id02"].setText(info.get("srv_id02", "—"))
        self.status_labels["srv_id03"].setText(info.get("srv_id03", "—"))

    def update_security_info(self, info: dict):
        self.sec_labels["cert_server"].setText(info.get("cert_server", "—"))
        self.sec_labels["pki_status"].setText(info.get("pki_status", "—"))
        self.sec_labels["cert_valid_date"].setText(info.get("cert_valid_date", "—"))
        self.sec_labels["key_slot_status"].setText(info.get("key_slot_status", "—"))
        self.sec_labels["tls_switch"].setText(info.get("tls_switch", "—"))
        self.sec_labels["secoc_switch"].setText(info.get("secoc_switch", "—"))
        self.sec_labels["cms_env"].setText(info.get("cms_env", "—"))

    def update_network_mgmt(self, info: dict):
        self.net_labels["power_wake_source"].setText(info.get("power_wake_source", "—"))
        self.net_labels["pnc"].setText(info.get("pnc", "—"))
        self.net_labels["rt1_net_source"].setText(info.get("rt1_net_source", "—"))
        self.net_labels["rt2_net_source"].setText(info.get("rt2_net_source", "—"))
        self.net_labels["rt1_ext_msg"].setText(info.get("rt1_ext_msg", "—"))
        self.net_labels["rt2_ext_msg"].setText(info.get("rt2_ext_msg", "—"))
        self.net_labels["a_core_net_req"].setText(info.get("a_core_net_req", "—"))
        self.net_labels["obd_can_net"].setText(info.get("obd_can_net", "—"))

    def update_storage_info(self, info: dict):
        self.storage_labels["a_core_storage"].setText(info.get("a_core_storage", "—"))
        self.storage_labels["m_core_storage"].setText(info.get("m_core_storage", "—"))


    def append_log(self, text: str):
        self.log_view.append(text)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = TopologyView()
    view.show()
    app.exec_()
