"""
@FileName：network_status_card.py
@Description：
@Author：QinHao
@Time：2025/11/26 13:25
@Department：PTV_AT
"""
from PyQt5 import QtWidgets, QtGui


class NetworkStatusCard(QtWidgets.QWidget):
    def __init__(self, network_name, status, traffic, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget { background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px; padding: 16px; }
            QWidget:hover { border-color: #3B82F6; background-color: #F8FAFC; }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        name_label = QtWidgets.QLabel(network_name)
        name_label.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Medium))
        name_label.setStyleSheet("color: #111827; border: none; padding: 0;")
        layout.addWidget(name_label)
        info_layout = QtWidgets.QHBoxLayout()
        info_layout.setSpacing(12)
        status_icon = QtWidgets.QLabel("✅" if status == "正常" else "❌")
        status_icon.setFont(QtGui.QFont("Segoe UI", 16))
        info_layout.addWidget(status_icon)
        traffic_label = QtWidgets.QLabel(traffic)
        traffic_label.setFont(QtGui.QFont("Segoe UI", 9))
        traffic_label.setStyleSheet("color: #4B5563; border: none; padding: 0; font-weight: 500;")
        info_layout.addWidget(traffic_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        traffic_value = float(traffic.split()[0])
        progress = QtWidgets.QProgressBar()
        progress.setRange(0, 20)
        progress.setValue(int(traffic_value))
        progress.setFormat("")
        progress.setStyleSheet("""
            QProgressBar { border: none; border-radius: 6px; background-color: #E5E7EB; height: 8px; text-align: center; }
            QProgressBar::chunk { background-color: #10B981; border-radius: 6px; }
        """)
        layout.addWidget(progress)
