from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QTreeWidget, QTreeWidgetItem, QStackedWidget,
                             QPushButton, QSplitter)
from PyQt5.QtCore import Qt
from app.common.ui.style import APP_STYLE
from app.modules.app_config.view.app_log_settings_page import AppLogSettingsPage
from app.modules.app_config.view.diagnostic_layer_settings_page import DiagnosticLayerSettingsPage
from app.modules.app_config.view.doip_settings_page import DoIPSettingsPage
from app.modules.app_config.view.domain_software_update_page import DomainSoftwareUpdatePage


class SettingsWindow(QWidget):
    """主设置窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("设置")
        self.resize(1000, 750)
        self.current_page = None
        self.init_ui()

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

        # 展开所有节点
        self.tree_widget.expandAll()

    def create_pages(self):
        """创建各个设置页面"""
        # DoIP设置页面
        self.doip_page = DoIPSettingsPage()
        self.stacked_widget.addWidget(self.doip_page)

        # Diagnostic Layer设置页面
        self.diag_layer_page = DiagnosticLayerSettingsPage()
        self.stacked_widget.addWidget(self.diag_layer_page)

        # Domain Software Update设置页面
        self.domain_update_page = DomainSoftwareUpdatePage()
        self.stacked_widget.addWidget(self.domain_update_page)

        # APP Log Settings页面
        self.app_log_page = AppLogSettingsPage()
        self.stacked_widget.addWidget(self.app_log_page)

    def on_tree_item_clicked(self, item, column):
        """树形结构点击事件"""
        page_id = item.data(0, Qt.UserRole)

        # 根据page_id切换到对应页面
        page_mapping = {
            "doip": self.doip_page,
            "diag_layer": self.diag_layer_page,
            "domain_update": self.domain_update_page,
            "app_log": self.app_log_page
        }

        if page_id in page_mapping:
            self.current_page = page_mapping[page_id]
            self.stacked_widget.setCurrentWidget(self.current_page)

    def on_ok_clicked(self):
        """OK按钮点击事件 - 保存所有页面设置并关闭窗口"""
        # 保存所有页面的设置
        if hasattr(self, 'doip_page'):
            self.doip_page.save_settings()
        if hasattr(self, 'diag_layer_page'):
            self.diag_layer_page.save_settings()
        if hasattr(self, 'domain_update_page'):
            self.domain_update_page.save_settings()
        if hasattr(self, 'app_log_page'):
            self.app_log_page.save_settings()

        self.close()

    def on_cancel_clicked(self):
        """Cancel按钮点击事件 - 不保存直接关闭窗口"""
        self.close()
