# python
from PyQt5 import QtWidgets, QtGui, QtCore
from app.common.ui.widgets import ModernButton
from app.modules.device_topology.view.connection_item import ConnectionItem
from app.modules.device_topology.view.network_status_card import NetworkStatusCard
from app.modules.device_topology.view.node_item import NodeItem
from app.presentation.views.base_view import BaseView


class TopologyView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(2)

        topo_group = QtWidgets.QGroupBox("车辆拓扑图")
        topo_layout = QtWidgets.QVBoxLayout()
        self.graphics = QtWidgets.QGraphicsView()
        self.scene = QtWidgets.QGraphicsScene(self.graphics)
        self.graphics.setScene(self.scene)
        self.graphics.setRenderHint(QtGui.QPainter.Antialiasing)
        self.graphics.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.graphics.setStyleSheet("background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px;")
        topo_layout.addWidget(self.graphics)
        topo_group.setLayout(topo_layout)

        network_panel = QtWidgets.QGroupBox("网络状态")
        network_layout = QtWidgets.QVBoxLayout()
        self.network_grid = QtWidgets.QGridLayout()
        network_layout.addLayout(self.network_grid)
        network_layout.addStretch()
        network_panel.setLayout(network_layout)

        splitter.addWidget(topo_group)
        splitter.addWidget(network_panel)
        splitter.setSizes([700, 400])
        layout.addWidget(splitter)

        # 信息块（替换原 Tab）
        self._init_info_blocks(layout)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.refresh_btn = ModernButton("刷新拓扑", "#0EA5E9", "🔄")
        btn_layout.addWidget(self.refresh_btn)
        layout.addLayout(btn_layout)

    def _init_info_blocks(self, parent_layout: QtWidgets.QVBoxLayout):
        container = QtWidgets.QWidget()
        blocks_layout = QtWidgets.QHBoxLayout(container)
        blocks_layout.setSpacing(12)
        blocks_layout.setContentsMargins(0, 0, 0, 0)

        # 车辆信息
        self.vehicle_group = QtWidgets.QGroupBox("车辆信息")
        v_layout = QtWidgets.QFormLayout()
        self.vehicle_labels = {
            "id": QtWidgets.QLabel("—"),
            "model": QtWidgets.QLabel("—"),
            "version": QtWidgets.QLabel("—")
        }
        v_layout.addRow("车辆ID：", self.vehicle_labels["id"])
        v_layout.addRow("车型：", self.vehicle_labels["model"])
        v_layout.addRow("版本：", self.vehicle_labels["version"])
        self.vehicle_group.setLayout(v_layout)
        blocks_layout.addWidget(self.vehicle_group)

        # 状态信息
        self.status_group = QtWidgets.QGroupBox("状态信息")
        s_layout = QtWidgets.QVBoxLayout()
        self.status_overall = QtWidgets.QLabel("总体状态：—")
        self.status_uptime = QtWidgets.QLabel("在线时长：—")
        self.status_alarm = QtWidgets.QLabel("告警数：—")
        s_layout.addWidget(self.status_overall)
        s_layout.addWidget(self.status_uptime)
        s_layout.addWidget(self.status_alarm)
        s_layout.addStretch()
        self.status_group.setLayout(s_layout)
        blocks_layout.addWidget(self.status_group)

        # 信息安全
        self.security_group = QtWidgets.QGroupBox("信息安全")
        sec_layout = QtWidgets.QVBoxLayout()
        self.sec_level = QtWidgets.QLabel("安全等级：—")
        self.sec_policy = QtWidgets.QLabel("最近策略更新时间：—")
        self.sec_events = QtWidgets.QLabel("异常事件数：—")
        sec_layout.addWidget(self.sec_level)
        sec_layout.addWidget(self.sec_policy)
        sec_layout.addWidget(self.sec_events)
        sec_layout.addStretch()
        self.security_group.setLayout(sec_layout)
        blocks_layout.addWidget(self.security_group)

        # 网络管理
        self.net_group = QtWidgets.QGroupBox("网络管理")
        net_layout = QtWidgets.QVBoxLayout()
        self.net_bw = QtWidgets.QLabel("带宽利用率：—")
        self.net_latency = QtWidgets.QLabel("平均延迟：—")
        self.net_loss = QtWidgets.QLabel("丢包率：—")
        net_layout.addWidget(self.net_bw)
        net_layout.addWidget(self.net_latency)
        net_layout.addWidget(self.net_loss)
        net_layout.addStretch()
        self.net_group.setLayout(net_layout)
        blocks_layout.addWidget(self.net_group)

        # 储存信息
        self.storage_group = QtWidgets.QGroupBox("储存信息")
        st_layout = QtWidgets.QFormLayout()
        self.storage_total = QtWidgets.QLabel("—")
        self.storage_used = QtWidgets.QLabel("—")
        self.storage_free = QtWidgets.QLabel("—")
        self.storage_write = QtWidgets.QLabel("—")
        st_layout.addRow("总容量：", self.storage_total)
        st_layout.addRow("已用容量：", self.storage_used)
        st_layout.addRow("剩余容量：", self.storage_free)
        st_layout.addRow("写入速率：", self.storage_write)
        self.storage_group.setLayout(st_layout)
        blocks_layout.addWidget(self.storage_group)

        # 平均分布
        for i in range(blocks_layout.count()):
            blocks_layout.setStretch(i, 1)

        parent_layout.addWidget(container)

    def populate(self, nodes, networks):
        self.scene.clear()
        node_items = []
        for name, icon, status, x, y in nodes:
            n = NodeItem(name, icon, status, x, y)
            self.scene.addItem(n)
            node_items.append((n, status))
        for node, status in node_items:
            line = ConnectionItem(QtCore.QPointF(0, 0), node.pos(), status)
            self.scene.addItem(line)
        self.scene.setSceneRect(-400, -250, 800, 500)
        self.graphics.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

        while self.network_grid.count():
            item = self.network_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for i, (name, status, traffic) in enumerate(networks):
            card = NetworkStatusCard(name, status, traffic)
            self.network_grid.addWidget(card, i // 2, i % 2)

    def update_vehicle_info(self, info: dict):
        self.vehicle_labels["id"].setText(info.get("id", "—"))
        self.vehicle_labels["model"].setText(info.get("model", "—"))
        self.vehicle_labels["version"].setText(info.get("version", "—"))


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = TopologyView()
    view.show()
    app.exec_()
