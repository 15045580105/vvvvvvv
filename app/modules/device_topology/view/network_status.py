# -*- coding: utf-8 -*-

from PyQt5 import QtWidgets
from typing import Dict

from app.common.ui.style import APP_STYLE
from app.common.ui.widgets import ModernButton
from app.modules.device_topology.view.network_topology_widget import NetworkTopologyWidget

BTN_COLORS = ("#2563EB", "#0EA5E9", "#14B8A6", "#10B981", "#F97316", "#EC4899", "#6366F1", "#8B5CF6")


class NetworkStatusPanel(QtWidgets.QWidget):
    """Network status board keeping the legacy layout but modern styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NetworkStatusPanel")
        self.diag_buttons: Dict[str, ModernButton] = {}
        self.status_inputs: Dict[str, QtWidgets.QLineEdit] = {}
        self._init_ui()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(16)

        # --- Sniff action row (same as legacy layout) ---
        sniff_row = QtWidgets.QHBoxLayout()
        sniff_row.setSpacing(12)
        self.pushButton_ccu_sniff = ModernButton("CCU数据抓包", "#2563EB", "🛰", dense=True)
        self.pushButton_ccu_sniff.setObjectName("pushButton_ccu_sniff")
        self.pushButton_idc_tbox_adc_fl_sniff = ModernButton("IDC/TBOX/ADC/FL数据抓包", "#0EA5E9", "🧪", dense=True)
        self.pushButton_idc_tbox_adc_fl_sniff.setObjectName("pushButton_idc_tbox_adc_fl_sniff")
        self.pushButton_ethernet_sniff = ModernButton("整车以太网数据抓包", "#14B8A6", "🌐", dense=True)
        self.pushButton_ethernet_sniff.setObjectName("pushButton_ethernet_sniff")
        for btn in (self.pushButton_ccu_sniff, self.pushButton_idc_tbox_adc_fl_sniff, self.pushButton_ethernet_sniff):
            btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            sniff_row.addWidget(btn)
        sniff_row.addStretch()
        main_layout.addLayout(sniff_row)

        # --- Diagnostics grid (buttons + read-only line edits) ---
        grid_wrapper = QtWidgets.QHBoxLayout()
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        button_defs = [
            ("pushButton_switch_fault", "Switch故障读取", "switch_fault"),
            ("pushButton_pfe_fault", "PFE故障读取", "pfe_fault"),
            ("pushButton_link_status", "Link状态读取", "link_status"),
            ("pushButton_port_txrx_count", "端口TX与RX数据与帧计数", "port_txrx"),
            ("pushButton_ping_idc", "ping IDC", "ping_idc"),
            ("pushButton_ping_adc", "ping ADC", "ping_adc"),
            ("pushButton_ping_tbox", "ping TBOX", "ping_tbox"),
            ("pushButton_ping_fl", "ping FL", "ping_fl"),
        ]

        for idx, (attr_name, text, key) in enumerate(button_defs):
            color = BTN_COLORS[idx % len(BTN_COLORS)]
            btn = ModernButton(text, color, dense=True)
            btn.setObjectName(attr_name)
            btn.setMinimumWidth(140)
            btn.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
            setattr(self, attr_name, btn)
            self.diag_buttons[key] = btn
            grid.addWidget(btn, 0, idx)

        line_edits = [
            ("lineEdit_switch_fault_2", "switch_fault"),
            ("lineEdit_pfe_fault", "pfe_fault"),
            ("lineEdit_link_status", "link_status"),
            ("lineEdit_port_txrx_count", "port_txrx"),
            ("lineEdit_ping_idc", "ping_idc"),
            ("lineEdit_ping_adc", "ping_adc"),
            ("lineEdit_ping_tbox", "ping_tbox"),
            ("lineEdit_ping_fl", "ping_fl"),
        ]

        for idx, (attr_name, key) in enumerate(line_edits):
            editor = QtWidgets.QLineEdit()
            editor.setObjectName(attr_name)
            editor.setReadOnly(True)
            editor.setPlaceholderText("结果显示")
            setattr(self, attr_name, editor)
            self.status_inputs[key] = editor
            grid.addWidget(editor, 1, idx)

        grid_wrapper.addLayout(grid)
        grid_wrapper.addStretch()
        main_layout.addLayout(grid_wrapper)
        main_layout.addWidget(NetworkTopologyWidget())
        main_layout.addStretch(1)

    # --- Public API -------------------------------------------------
    def set_status(self, key: str, value: str):
        widget = self.status_inputs.get(key)
        if widget:
            widget.setText(value)

    def set_status_bulk(self, mapping: Dict[str, str]):
        for key, value in mapping.items():
            self.set_status(key, value)

    def button(self, key: str) -> ModernButton | None:
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
