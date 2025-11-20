# app/modules/device_management/device_management_view.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView,
                             QPushButton, QLabel, QToolBar, QHeaderView)
from PyQt5.QtCore import Qt, pyqtSignal


class DeviceManagementView(BaseView):
    """设备管理视图"""

    # 视图信号
    device_selected = pyqtSignal(str)  # 设备ID
    connect_requested = pyqtSignal(str)  # 设备ID
    disconnect_requested = pyqtSignal(str)  # 设备ID
    refresh_requested = pyqtSignal()  # 刷新请求

    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self._setup_ui()

    def _setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)

        # 工具栏
        toolbar = QToolBar()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        toolbar.addWidget(refresh_btn)

        layout.addWidget(toolbar)

        # 设备表格
        self.device_table = QTableView()
        self.device_table.setSelectionBehavior(QTableView.SelectRows)
        self.device_table.doubleClicked.connect(self._on_device_double_clicked)
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.device_table)

        # 操作按钮
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("连接设备")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        button_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("断开设备")
        self.disconnect_btn.clicked.connect(self._on_disconnect_clicked)
        button_layout.addWidget(self.disconnect_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # 状态标签
        self.status_label = QLabel("就绪")
        layout.addWidget(self.status_label)

    def update_display(self, data: dict):
        """更新显示"""
        # 这里实现具体的UI更新逻辑
        devices = data.get('devices', [])
        timestamp = data.get('timestamp', '')

        # 更新表格模型
        # self._update_table_model(devices)

        # 更新状态
        self.status_label.setText(f"数据更新时间: {timestamp}")

    def on_operation_completed(self, operation: str, success: bool):
        """操作完成回调"""
        if success:
            self.status_label.setText(f"操作 {operation} 成功")
        else:
            self.status_label.setText(f"操作 {operation} 失败")

    def _on_device_double_clicked(self, index):
        """设备双击事件"""
        # 获取选中的设备ID
        device_id = self._get_selected_device_id()
        if device_id:
            self.device_selected.emit(device_id)

    def _on_connect_clicked(self):
        """连接按钮点击"""
        device_id = self._get_selected_device_id()
        if device_id:
            self.connect_requested.emit(device_id)

    def _on_disconnect_clicked(self):
        """断开按钮点击"""
        device_id = self._get_selected_device_id()
        if device_id:
            self.disconnect_requested.emit(device_id)

    def _get_selected_device_id(self) -> str:
        """获取选中的设备ID"""
        # 这里实现获取选中设备ID的逻辑
        return "device_001"  # 示例返回值