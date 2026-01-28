# python
from PyQt5 import QtWidgets

from app.common.log.operation_log_manager import OperationLogManager
from app.common.ui.widgets import ModernButton
from app.modules.device_topology.view.topology_widget import SimpleTopologyWindow, CanLinTopologyWindow
from app.presentation.views.base_view import BaseView
from PyQt5.QtCore import QDateTime


class TopologyView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        # 1. 拓扑图区域 (包含悬浮工具栏)
        topo_group = QtWidgets.QGroupBox("车辆拓扑图")
        topo_layout = QtWidgets.QVBoxLayout()

        # 刷新按钮放在拓扑图上方
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.refresh_btn = ModernButton("刷新拓扑", "#0EA5E9", "🔄")
        btn_layout.addWidget(self.refresh_btn)
        topo_layout.addLayout(btn_layout)

        self.tab_widget = QtWidgets.QTabWidget()

        self.graphics = SimpleTopologyWindow()
        # 获取内部的 TopologyWidget 实例以便后续调用更新方法
        self.topology_widget = self.graphics.topology
        self.tab_widget.addTab(self.graphics, "以太网拓扑")

        self.graphics_can_lin = CanLinTopologyWindow()
        self.tab_widget.addTab(self.graphics_can_lin, "CAN/LIN网络拓扑")

        topo_layout.addWidget(self.tab_widget)
        topo_group.setLayout(topo_layout)

        layout.addWidget(topo_group, 3)

        # 2. 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(130)
        self.log_view.setPlaceholderText("这里显示拓扑相关的操作日志...")
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, 1)

        # 暴露 network_status_panel 给 controller 使用
        # 注意：现在它位于 topology_widget 的悬浮面板中
        self.network_status_panel = self.topology_widget.network_diag_widget

    def update_vehicle_info(self, info: dict):
        self.topology_widget.update_vehicle_info(info)

    def update_service_status_info(self, info: dict):
        self.topology_widget.update_service_status_info(info)

    def update_security_info(self, info: dict):
        self.topology_widget.update_security_info(info)

    def update_network_mgmt(self, info: dict):
        self.topology_widget.update_network_mgmt(info)

    def update_storage_info(self, info: dict):
        self.topology_widget.update_storage_info(info)

    def update_version_info(self, info: dict):
        self.topology_widget.update_version_info(info)

    def set_loading(self, loading: bool):
        """设置加载状态"""
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.setEnabled(not loading)
            self.refresh_btn.setText("刷新中..." if loading else "刷新拓扑")

    def append_log(self, text: str):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        log_msg = f"[{timestamp}] {text}"
        self.log_view.append(log_msg)
        OperationLogManager.instance().append_log("设备拓扑", text)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = TopologyView()
    view.show()
    app.exec_()
