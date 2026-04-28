from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QTreeWidget, QTreeWidgetItem, QStackedWidget,
                             QPushButton, QSplitter)
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from app.common.ui.style import APP_STYLE
from app.modules.app_config.view.app_log_settings_page import AppLogSettingsPage
from app.modules.app_config.view.diagnostic_layer_settings_page import DiagnosticLayerSettingsPage
from app.modules.app_config.view.doip_settings_page import DoIPSettingsPage
from app.modules.app_config.view.someip_settings_page import SomeIPSettingsPage
from app.modules.app_config.view.domain_software_update_page import DomainSoftwareUpdatePage
from app.modules.app_config.view.license_info_page import LicenseInfoPage


class SettingsWindow(QWidget):
    """主设置窗口"""
    # Define signals for save transaction
    save_started = QtCore.pyqtSignal()
    save_finished = QtCore.pyqtSignal()
    window_shown = QtCore.pyqtSignal()  # New signal

    def __init__(self):
        super().__init__()
        self.setWindowTitle("设置")
        self.resize(1000, 750)
        self.current_page = None
        self._someip_import_in_progress = False
        self.init_ui()

    def showEvent(self, event):
        """Override showEvent to emit signal"""
        super().showEvent(event)
        self.window_shown.emit()

    def init_ui(self):
        """初始化界面"""
        # 应用全局样式
        self.setStyleSheet(APP_STYLE)

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 分割器（树和页面）
        splitter = QSplitter(Qt.Horizontal)

        # 左侧树形导航
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("设置分类")
        self.tree_widget.setMaximumWidth(280)
        self.tree_widget.setMinimumWidth(220)
        # 样式已由 APP_STYLE 覆盖，这里只需微调
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                border-right: 1px solid #E5E7EB;
            }
        """)

        # 创建树形结构
        self.create_tree_structure()

        # 右侧堆叠窗口
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("background-color: #FFFFFF;")

        # 创建并添加设置页面
        self.create_pages()

        # 将树和堆叠窗口添加到分割器
        splitter.addWidget(self.tree_widget)
        splitter.addWidget(self.stacked_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #E5E7EB;
            }
        """)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(20, 15, 20, 15)

        button_layout.addStretch()

        self.ok_button = QPushButton("确定")
        self.ok_button.setFixedWidth(90)
        self.ok_button.setCursor(Qt.PointingHandCursor)
        # 使用主题蓝色
        self.ok_button.setStyleSheet(self._get_button_style("#3B82F6", "#2563EB", "#1D4ED8"))
        self.ok_button.clicked.connect(self.on_ok_clicked)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setFixedWidth(90)
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        # 使用主题灰色
        self.cancel_button.setStyleSheet(self._get_button_style("#9CA3AF", "#6B7280", "#4B5563"))
        self.cancel_button.clicked.connect(self.on_cancel_clicked)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)

        # 底部按钮容器背景
        button_container = QWidget()
        button_container.setStyleSheet("background-color: #F9FAFB; border-top: 1px solid #E5E7EB;")
        button_container.setLayout(button_layout)

        # 组装主布局
        main_layout.addWidget(splitter)
        main_layout.addWidget(button_container)

        self.setLayout(main_layout)

        # 连接树形结构点击事件
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)

        # 默认选中第一个页面
        self.tree_widget.setCurrentItem(self.tree_widget.topLevelItem(0).child(0))
        self.stacked_widget.setCurrentIndex(0)
        self.current_page = self.doip_page

    def _get_button_style(self, bg_color, hover_color, pressed_color):
        """获取按钮样式"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
        """

    def create_tree_structure(self):
        """创建树形结构"""
        # Protocol Stack节点
        protocol_item = QTreeWidgetItem(self.tree_widget)
        protocol_item.setText(0, "协议栈")

        # Protocol Stack子节点
        doip_item = QTreeWidgetItem(protocol_item)
        doip_item.setText(0, "DoIP 设置")
        doip_item.setData(0, Qt.UserRole, "doip")

        someip_item = QTreeWidgetItem(protocol_item)
        someip_item.setText(0, "SomeIP 设置")
        someip_item.setData(0, Qt.UserRole, "someip")

        diag_layer_item = QTreeWidgetItem(protocol_item)
        diag_layer_item.setText(0, "诊断层")
        diag_layer_item.setData(0, Qt.UserRole, "diag_layer")

        # Tool Settings节点
        tool_settings_item = QTreeWidgetItem(self.tree_widget)
        tool_settings_item.setText(0, "工具设置")

        # Tool Settings子节点
        domain_update_item = QTreeWidgetItem(tool_settings_item)
        domain_update_item.setText(0, "域软件升级")
        domain_update_item.setData(0, Qt.UserRole, "domain_update")

        # APP Log Settings节点
        app_log_item = QTreeWidgetItem(self.tree_widget)
        app_log_item.setText(0, "APP 日志设置")
        app_log_item.setData(0, Qt.UserRole, "app_log")

        help_item = QTreeWidgetItem(self.tree_widget)
        help_item.setText(0, "帮助")

        license_item = QTreeWidgetItem(help_item)
        license_item.setText(0, "License")
        license_item.setData(0, Qt.UserRole, "license")

        # 展开所有节点
        self.tree_widget.expandAll()

    def create_pages(self):
        """创建各个设置页面"""
        # DoIP设置页面
        self.doip_page = DoIPSettingsPage()
        self.stacked_widget.addWidget(self.doip_page)

        # SomeIP设置页面
        self.someip_page = SomeIPSettingsPage()
        self.stacked_widget.addWidget(self.someip_page)

        # Diagnostic Layer设置页面
        self.diag_layer_page = DiagnosticLayerSettingsPage()
        self.stacked_widget.addWidget(self.diag_layer_page)

        # Domain Software Update设置页面
        self.domain_update_page = DomainSoftwareUpdatePage()
        self.stacked_widget.addWidget(self.domain_update_page)

        # APP Log Settings页面
        self.app_log_page = AppLogSettingsPage()
        self.stacked_widget.addWidget(self.app_log_page)

        self.license_page = LicenseInfoPage()
        self.stacked_widget.addWidget(self.license_page)

    def on_tree_item_clicked(self, item, column):
        """树形结构点击事件"""
        page_id = item.data(0, Qt.UserRole)

        # 根据page_id切换到对应页面
        page_mapping = {
            "doip": self.doip_page,
            "diag_layer": self.diag_layer_page,
            "domain_update": self.domain_update_page,
            "app_log": self.app_log_page,
            "someip": self.someip_page,
            "license": self.license_page,
        }

        if page_id in page_mapping:
            self.current_page = page_mapping[page_id]
            self.stacked_widget.setCurrentWidget(self.current_page)
            if hasattr(self.current_page, "refresh_license_info"):
                self.current_page.refresh_license_info()

    def select_page(self, page_id: str, focus_target: str | None = None):
        target_item = None
        root_count = self.tree_widget.topLevelItemCount()
        for i in range(root_count):
            root = self.tree_widget.topLevelItem(i)
            stack = [root]
            while stack:
                item = stack.pop(0)
                if item.data(0, Qt.UserRole) == page_id:
                    target_item = item
                    break
                for child_index in range(item.childCount()):
                    stack.append(item.child(child_index))
            if target_item:
                break

        if target_item is not None:
            self.tree_widget.setCurrentItem(target_item)
            self.on_tree_item_clicked(target_item, 0)

        if page_id == "doip" and focus_target == "network_interface":
            QtCore.QTimer.singleShot(120, self.doip_page.focus_network_interface)

    def _collect_all_settings(self) -> dict:
        """Collect settings from all pages without persisting."""
        settings: dict = {}

        # NOTE: these pages already know how to extract their UI state
        # We call page-level helpers rather than emitting signals.
        if hasattr(self, 'doip_page'):
            settings["doip"] = {
                "protocol_version": self.doip_page.protocol_version_combo.currentIndex(),
                "logical_addr": self.doip_page.logical_addr_edit.text(),
                "routing_type": self.doip_page.routing_type_edit.text(),
                "routing_request": self.doip_page.routing_request_check.isChecked(),
                "network_interface": self.doip_page.network_combo.currentIndex(),
                "network_interface_ip": self.doip_page.network_combo.currentData(),
                "target_phy_addr": self.doip_page.phy_addr_edit.text(),
                "target_fun_addr": self.doip_page.fun_addr_edit.text(),
                "target_addr_mode": int(self.doip_page.addr_group.checkedId()),
                "dpt_file": self.doip_page.dpt_path_edit.text(),
            }

        if hasattr(self, 'someip_page'):
            settings["someip"] = {
                "local_ip": self.someip_page.network_combo.currentData(),
                "matrix_file": self.someip_page.matrix_file_edit.text().strip(),
            }

        if hasattr(self, 'diag_layer_page'):
            settings["diag_layer"] = {
                "s3_client_time": self.diag_layer_page.s3_client_edit.text(),
                "s3_server_time": self.diag_layer_page.s3_server_edit.text(),
                "dll_path": self.diag_layer_page.dll_path_edit.text(),
                "physical_addr": self.diag_layer_page.physical_addr_edit.text(),
                "functional_addr": self.diag_layer_page.functional_addr_edit.text(),
                "ecu_config_path": self.diag_layer_page.ecu_file_edit.text(),
                "target_ecu_name": self.diag_layer_page.target_ecu_combo.currentText(),
                "diag_addr_mode": int(self.diag_layer_page.addr_group.checkedId()),
            }

        if hasattr(self, 'domain_update_page'):
            settings["domain_update"] = {
                "success_delay": self.domain_update_page.success_delay_edit.text(),
                "failure_delay": self.domain_update_page.failure_delay_edit.text(),
                "ecu_reset": self.domain_update_page.ecu_reset_check.isChecked(),
                "stop_on_failure": self.domain_update_page.stop_on_failure_check.isChecked(),
            }

        if hasattr(self, 'app_log_page'):
            settings["app_log"] = {
                "export_path": self.app_log_page.export_path_edit.text(),
                "export_module": self.app_log_page.export_module_combo.currentText(),
            }

        # Sanitize to primitives
        for section, data in list(settings.items()):
            if isinstance(data, dict):
                for k, v in list(data.items()):
                    if v is None:
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        continue
                    data[k] = str(v)

        return settings

    def set_someip_import_in_progress(self, in_progress: bool):
        self._someip_import_in_progress = in_progress
        self.ok_button.setEnabled(not in_progress)
        self.cancel_button.setEnabled(not in_progress)

    def closeEvent(self, event):
        if self._someip_import_in_progress:
            event.ignore()
            return
        super().closeEvent(event)

    def on_ok_clicked(self):
        """OK按钮点击事件 - 保存所有页面设置并关闭窗口"""
        if self._someip_import_in_progress:
            return
        # Emit signal to start batch save
        self.save_started.emit()

        try:
            # Collect all settings once; actual persistence is handled by controller
            all_settings = self._collect_all_settings()
            # attach to instance for controller to pick up
            self._pending_all_settings = all_settings
        finally:
            # Emit signal to finish batch save and write to disk
            self.save_finished.emit()
            self.close()

    def on_cancel_clicked(self):
        """Cancel按钮点击事件 - 不保存直接关闭窗口"""
        if self._someip_import_in_progress:
            return
        self.close()
