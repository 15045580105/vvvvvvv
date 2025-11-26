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
        self.info_tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.info_tabs)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.export_btn = ModernButton("导出拓扑报告", "#059669", "📊")
        self.refresh_btn = ModernButton("刷新拓扑", "#0EA5E9", "🔄")
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.refresh_btn)
        layout.addLayout(btn_layout)

    def populate(self, nodes, networks):
        self.scene.clear()
        node_items = []
        for name, icon, status, x, y in nodes:
            n = NodeItem(name, icon, status, x, y)
            self.scene.addItem(n)
            node_items.append((n, status))
        for node, status in node_items:
            line = ConnectionItem(QtCore.QPointF(0,0), node.pos(), status)
            self.scene.addItem(line)
        self.scene.setSceneRect(-400, -250, 800, 500)
        self.graphics.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
        # networks
        while self.network_grid.count():
            item = self.network_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for i,(name,status,traffic) in enumerate(networks):
            card = NetworkStatusCard(name,status,traffic)
            self.network_grid.addWidget(card, i//2, i%2)
