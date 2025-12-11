# -*- coding: utf-8 -*-

from PyQt5 import QtWidgets
from typing import Dict, Optional

from app.common.ui.style import APP_STYLE
from app.common.ui.widgets import ModernButton

BTN_COLORS = ("#2563EB", "#0EA5E9", "#14B8A6", "#10B981", "#F97316", "#EC4899", "#6366F1", "#8B5CF6")


class NetworkStatusPanel(QtWidgets.QWidget):
    """Network status board: three vertical sections with capture, status, and ping blocks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NetworkStatusPanel")
        self.diag_buttons: Dict[str, ModernButton] = {}
        self.status_inputs: Dict[str, QtWidgets.QLineEdit] = {}
        self._init_ui()

    def _init_ui(self):
        from PyQt5.QtWidgets import QSizePolicy
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(6)

        # === Section 1: Capture buttons =====================================
        capture_layout = QtWidgets.QHBoxLayout()
        capture_layout.setSpacing(8)

        # CCU ETH 数据抓包
        self.pushButton_ccu_eth_capture = ModernButton("CCU ETH数据抓包", BTN_COLORS[0], dense=True)
        self.pushButton_ccu_eth_capture.setObjectName("pushButton_ccu_eth_capture")
        self.pushButton_ccu_eth_capture.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.pushButton_ccu_eth_capture.setFixedHeight(40)
        self._register_button("capture_ccu_eth", self.pushButton_ccu_eth_capture)
        capture_layout.addWidget(self.pushButton_ccu_eth_capture)

        # IDC/ADC/IFC/TBOX/FL 节点 ETH 数据抓包
        self.pushButton_node_eth_capture = ModernButton("IDC/ADC/IFC/TBOX/FL节点ETH数据抓包", BTN_COLORS[1], dense=True)
        self.pushButton_node_eth_capture.setObjectName("pushButton_node_eth_capture")
        self.pushButton_node_eth_capture.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.pushButton_node_eth_capture.setFixedHeight(40)
        self._register_button("capture_node_eth", self.pushButton_node_eth_capture)
        capture_layout.addWidget(self.pushButton_node_eth_capture)

        # 整车 ETH 数据抓包
        self.pushButton_vehicle_eth_capture = ModernButton("整车ETH数据抓包", BTN_COLORS[2], dense=True)
        self.pushButton_vehicle_eth_capture.setObjectName("pushButton_vehicle_eth_capture")
        self.pushButton_vehicle_eth_capture.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.pushButton_vehicle_eth_capture.setFixedHeight(40)
        self._register_button("capture_vehicle_eth", self.pushButton_vehicle_eth_capture)
        capture_layout.addWidget(self.pushButton_vehicle_eth_capture)

        capture_layout.addStretch(1)
        main_layout.addLayout(capture_layout, stretch=1)

        # === Section 2: Status read (2 rows x 3 columns: button above, status below) ===
        status_grid = QtWidgets.QGridLayout()
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(6)

        # Column 0: Switch 故障读取 + Switch 状态显示
        self.pushButton_switch_fault = ModernButton("Switch故障读取", BTN_COLORS[3], dense=True)
        self.pushButton_switch_fault.setObjectName("pushButton_switch_fault")
        self.pushButton_switch_fault.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.pushButton_switch_fault.setFixedHeight(40)
        self._register_button("read_switch_fault", self.pushButton_switch_fault)
        status_grid.addWidget(self.pushButton_switch_fault, 0, 0)

        self.lineEdit_switch_status = QtWidgets.QLineEdit()
        self.lineEdit_switch_status.setObjectName("lineEdit_switch_status")
        self.lineEdit_switch_status.setReadOnly(True)
        self.lineEdit_switch_status.setPlaceholderText("Switch状态显示")
        self.lineEdit_switch_status.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.lineEdit_switch_status.setStyleSheet("font-size: 16px;")
        self.lineEdit_switch_status.setFixedHeight(40)
        self._register_status("switch_status", self.lineEdit_switch_status)
        status_grid.addWidget(self.lineEdit_switch_status, 1, 0)

        # Column 1: NTL 故障读取 + PFE 状态显示
        self.pushButton_ntl_fault = ModernButton("NTL故障读取", BTN_COLORS[4], dense=True)
        self.pushButton_ntl_fault.setObjectName("pushButton_ntl_fault")
        self.pushButton_ntl_fault.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.pushButton_ntl_fault.setFixedHeight(40)
        self._register_button("read_ntl_fault", self.pushButton_ntl_fault)
        status_grid.addWidget(self.pushButton_ntl_fault, 0, 1)

        self.lineEdit_pfe_status = QtWidgets.QLineEdit()
        self.lineEdit_pfe_status.setObjectName("lineEdit_pfe_status")
        self.lineEdit_pfe_status.setReadOnly(True)
        self.lineEdit_pfe_status.setPlaceholderText("PFE状态显示")
        self.lineEdit_pfe_status.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.lineEdit_pfe_status.setStyleSheet("font-size: 16px;")
        self.lineEdit_pfe_status.setFixedHeight(40)
        self._register_status("pfe_status", self.lineEdit_pfe_status)
        status_grid.addWidget(self.lineEdit_pfe_status, 1, 1)

        # Column 2: TX 与 RX 数据计数 + 统计接口显示
        self.pushButton_txrx_count = ModernButton("TX与RX数据计数", BTN_COLORS[5], dense=True)
        self.pushButton_txrx_count.setObjectName("pushButton_txrx_count")
        self.pushButton_txrx_count.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.pushButton_txrx_count.setFixedHeight(40)
        self._register_button("tx_rx_data_count", self.pushButton_txrx_count)
        status_grid.addWidget(self.pushButton_txrx_count, 0, 2)

        self.lineEdit_txrx_stats = QtWidgets.QLineEdit()
        self.lineEdit_txrx_stats.setObjectName("lineEdit_txrx_stats")
        self.lineEdit_txrx_stats.setReadOnly(True)
        self.lineEdit_txrx_stats.setPlaceholderText("TX与RX数据统计接口显示")
        self.lineEdit_txrx_stats.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.lineEdit_txrx_stats.setStyleSheet("font-size: 16px;")
        self.lineEdit_txrx_stats.setFixedHeight(40)
        self._register_status("tx_rx_stats", self.lineEdit_txrx_stats)
        status_grid.addWidget(self.lineEdit_txrx_stats, 1, 2)

        for col in range(3):
            status_grid.setColumnStretch(col, 1)
        status_grid.setRowStretch(0, 1)
        status_grid.setRowStretch(1, 1)

        main_layout.addLayout(status_grid, stretch=1)

        # === Section 3: Ping buttons (2 rows x 7 columns) ====================
        ping_grid = QtWidgets.QGridLayout()
        ping_grid.setHorizontalSpacing(6)
        ping_grid.setVerticalSpacing(4)

        # Helper for creating ping button + result line edit
        def add_ping_item(col: int, label: str, key_suffix: str):
            btn = ModernButton(f"Ping {label}", BTN_COLORS[col % len(BTN_COLORS)], dense=True)
            btn.setObjectName(f"pushButton_ping_{key_suffix}")
            btn.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
            btn.setFixedHeight(40)
            self._register_button(f"ping_{key_suffix}", btn)
            ping_grid.addWidget(btn, 0, col)

            line_edit = QtWidgets.QLineEdit()
            line_edit.setObjectName(f"lineEdit_ping_{key_suffix}")
            line_edit.setReadOnly(True)
            line_edit.setPlaceholderText(f"Ping {label} 结果显示")
            line_edit.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
            line_edit.setStyleSheet("font-size: 15px;")
            line_edit.setFixedHeight(40)
            self._register_status(f"ping_{key_suffix}_result", line_edit)
            ping_grid.addWidget(line_edit, 1, col)

        ping_nodes = [
            (0, "ADC", "adc"),
            (1, "IDC", "idc"),
            (2, "TBOX", "tbox"),
            (3, "FL", "fl"),
            (4, "IFC", "ifc"),
            (5, "RT1", "rt1"),
            (6, "RT2", "rt2"),
        ]
        for col, label, key in ping_nodes:
            add_ping_item(col, label, key)

        # 让 7 列平均拉伸，同时行也有一定高度
        for col in range(7):
            ping_grid.setColumnStretch(col, 1)
        ping_grid.setRowStretch(0, 1)
        ping_grid.setRowStretch(1, 1)

        main_layout.addLayout(ping_grid, stretch=1)

    # --- helpers ------------------------------------------------------------
    def _register_button(self, key: str, button: ModernButton) -> None:
        self.diag_buttons[key] = button

    def _register_status(self, key: str, widget: QtWidgets.QLineEdit) -> None:
        self.status_inputs[key] = widget

    # --- Public API ---------------------------------------------------------
    def set_status(self, key: str, value: str):
        widget = self.status_inputs.get(key)
        if widget is not None:
            widget.setText(value)

    def set_status_bulk(self, mapping: Dict[str, str]):
        for key, value in mapping.items():
            self.set_status(key, value)

    def button(self, key: str) -> Optional[ModernButton]:
        return self.diag_buttons.get(key)


__all__ = ["NetworkStatusPanel"]

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    panel = NetworkStatusPanel()
    panel.resize(1280, 480)
    panel.show()
    sys.exit(app.exec_())
