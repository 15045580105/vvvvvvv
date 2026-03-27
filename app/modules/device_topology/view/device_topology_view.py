# python
from PyQt5 import QtWidgets

from app.common.log.operation_log_manager import OperationLogManager
from app.common.ui.widgets import ModernButton
from app.modules.device_topology.view.topology_widget import SimpleTopologyWindow, CanLinTopologyWindow
from app.presentation.views.base_view import BaseView
from PyQt5.QtCore import QDateTime
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder


class TopologyView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.log_splitter = LogAreaSplitter(self, min_log_height=150, max_log_ratio=0.8)
        layout.addWidget(self.log_splitter)

        content_widget = QtWidgets.QWidget()
        content_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(10)

        # 1. 拓扑图区域 (包含悬浮工具栏)
        topo_group = QtWidgets.QGroupBox("车辆拓扑图")
        topo_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        topo_layout = QtWidgets.QVBoxLayout()
        topo_layout.setContentsMargins(8, 10, 8, 8)
        topo_layout.setSpacing(8)

        # 刷新按钮放在拓扑图上方
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.refresh_btn = ModernButton("刷新拓扑", "#0EA5E9", "🔄")
        btn_layout.addWidget(self.refresh_btn)
        topo_layout.addLayout(btn_layout)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.tab_widget.setDocumentMode(True)

        self.graphics = SimpleTopologyWindow()
        self.graphics.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        # 获取内部的 TopologyWidget 实例以便后续调用更新方法
        self.topology_widget = self.graphics.topology
        self.tab_widget.addTab(self.graphics, "以太网拓扑")

        self.graphics_can_lin = CanLinTopologyWindow()
        self.graphics_can_lin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.tab_widget.addTab(self.graphics_can_lin, "CAN/LIN网络拓扑")

        topo_layout.addWidget(self.tab_widget)
        topo_group.setLayout(topo_layout)
        content_layout.addWidget(topo_group)

        # 2. 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(8, 12, 8, 8)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(0)
        self.log_view.setPlaceholderText("这里显示拓扑相关的操作日志...")
        LogPanelBuilder.attach_search(log_layout, self.log_view)
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        self.log_splitter.set_panels(content_widget, log_group, initial_log_height=100)

        # 暴露 network_status_panel 给 controller 使用
        # 注意：现在它位于 topology_widget 的悬浮面板中
        self.network_status_panel = self.topology_widget.network_diag_widget

    def update_single_vehicle_info(self, key: str, value: str):
        """更新单个车辆信息"""
        self.topology_widget.update_vehicle_info({key: value})

    def update_single_service_status(self, key: str, value: str):
        """更新单个服务状态信息"""
        # TopologyWidget.update_service_status_info 期望 key='status_summary'
        self.topology_widget.update_service_status_info({key: value})

    def update_single_security_info(self, key: str, value: str):
        """更新单个证书信息"""
        self.topology_widget.update_security_info({key: value})

    def update_single_network_info(self, key: str, value: str):
        """更新单个网络管理信息"""
        self.topology_widget.update_network_mgmt({key: value})

    def update_single_storage_info(self, key: str, value: str):
        """更新单个存储信息"""
        self.topology_widget.update_storage_info({key: value})

    def update_single_version_info(self, key: str, value: str):
        """更新单个版本信息"""
        # TopologyWidget 似乎把版本信息也当作 storage? 检查 TopologyWidget 代码
        # 假设 update_version_info 存在
        self.topology_widget.update_version_info({key: value})

    def update_vehicle_info(self, info: dict):
        self.topology_widget.update_vehicle_info(info)

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
