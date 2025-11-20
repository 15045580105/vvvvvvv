# 主窗口
import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTreeWidget, QTreeWidgetItem, QSplitter,
                             QStackedWidget, QLabel, QFrame, QToolBar, QAction,
                             QStatusBar, QMenuBar, QMessageBox, QPushButton)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QFont, QPalette, QColor


class MainWindow(QMainWindow):
    """GAC诊断工具主窗口 - 左侧菜单栏 + 右侧内容面板设计"""

    # 信号定义
    menu_item_selected = pyqtSignal(str, str)  # 一级菜单, 二级菜单

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GAC诊断工具-设备状态管理系统")
        self.setGeometry(100, 50, 1400, 900)

        # 当前选中的菜单项
        self.current_first_level = ""
        self.current_second_level = ""

        # 初始化UI
        self.setup_ui()
        self.setup_menu_bar()
        self.setup_status_bar()

        # 应用样式
        self.apply_styles()

    def setup_ui(self):
        """设置主界面布局"""
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局 - 水平分割
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧菜单栏
        self.setup_left_menu(splitter)

        # 右侧内容面板
        self.setup_right_panel(splitter)

        # 设置分割器比例
        splitter.setStretchFactor(0, 1)  # 左侧菜单固定宽度
        splitter.setStretchFactor(1, 4)  # 右侧内容区域可伸缩

        # 设置初始分割比例
        splitter.setSizes([300, 1100])

        main_layout.addWidget(splitter)

    def setup_left_menu(self, parent):
        """设置左侧菜单栏"""
        # 创建菜单容器
        menu_frame = QFrame()
        menu_frame.setFrameStyle(QFrame.StyledPanel)
        menu_layout = QVBoxLayout(menu_frame)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(0)

        # 菜单标题
        title_label = QLabel("功能菜单")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        title_label.setFixedHeight(40)
        menu_layout.addWidget(title_label)

        # 创建树形菜单
        self.menu_tree = QTreeWidget()
        self.menu_tree.setHeaderHidden(True)
        self.menu_tree.setIndentation(15)

        # 设置菜单项样式
        self.menu_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2c3e50;
                color: white;
                border: none;
                outline: 0;
            }
            QTreeWidget::item {
                height: 40px;
                padding-left: 10px;
                border-bottom: 1px solid #34495e;
            }
            QTreeWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #34495e;
            }
        """)

        # 添加菜单项
        self.setup_menu_items()

        # 连接菜单点击事件
        self.menu_tree.itemClicked.connect(self.on_menu_item_clicked)

        menu_layout.addWidget(self.menu_tree)

        parent.addWidget(menu_frame)

    def setup_menu_items(self):
        """设置菜单项 - 根据图片描述创建一二级菜单"""
        # 一级菜单项
        first_level_items = [
            ("设备状态管理", "device_management"),
            ("DTC故障诊断", "dtc_diagnostic"),
            ("DID数据管理", "did_management"),
            ("文件传输管理", "file_transfer"),
            ("设备升级管理", "device_upgrade"),
            ("配置管理中心", "configuration")
        ]

        # 二级菜单项映射
        second_level_items = {
            "device_management": [
                ("拓扑状态查询", "topology_query"),
                ("性能状态查询", "performance_query"),
                ("进程状态查询", "process_query")
            ],
            "dtc_diagnostic": [
                ("当前故障码", "current_dtc"),
                ("历史故障码", "historical_dtc"),
                ("故障码清除", "clear_dtc")
            ],
            "did_management": [
                ("DID数据读取", "did_read"),
                ("DID数据写入", "did_write"),
                ("DID数据监控", "did_monitor")
            ],
            "file_transfer": [
                ("文件上传", "file_upload"),
                ("文件下载", "file_download"),
                ("文件管理", "file_management")
            ],
            "device_upgrade": [
                ("软件升级", "software_upgrade"),
                ("固件升级", "firmware_upgrade"),
                ("升级记录", "upgrade_history")
            ],
            "configuration": [
                ("系统设置", "system_settings"),
                ("通信配置", "communication_config"),
                ("用户管理", "user_management")
            ]
        }

        # 添加一级菜单和二级菜单
        for first_text, first_key in first_level_items:
            first_item = QTreeWidgetItem(self.menu_tree)
            first_item.setText(0, first_text)
            first_item.setData(0, Qt.UserRole, {"type": "first", "key": first_key})

            # 设置一级菜单图标（如果有的话）
            # first_item.setIcon(0, QIcon(":/icons/device.png"))

            # 添加二级菜单
            if first_key in second_level_items:
                for second_text, second_key in second_level_items[first_key]:
                    second_item = QTreeWidgetItem(first_item)
                    second_item.setText(0, second_text)
                    second_item.setData(0, Qt.UserRole, {
                        "type": "second",
                        "first_key": first_key,
                        "second_key": second_key
                    })

            # 展开一级菜单
            first_item.setExpanded(True)

    def setup_right_panel(self, parent):
        """设置右侧内容面板"""
        # 创建右侧面板容器
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 顶部标题栏
        self.setup_title_bar(right_layout)

        # 内容堆叠窗口
        self.content_stack = QStackedWidget()
        self.setup_content_pages()

        right_layout.addWidget(self.content_stack)

        parent.addWidget(right_frame)

    def setup_title_bar(self, layout):
        """设置顶部标题栏"""
        title_frame = QFrame()
        title_frame.setFixedHeight(60)
        title_frame.setStyleSheet("""
            QFrame {
                background-color: #3498db;
                border-bottom: 2px solid #2980b9;
            }
        """)

        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(20, 0, 20, 0)

        # 标题文本
        self.title_label = QLabel("欢迎使用GAC诊断工具")
        self.title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        self.title_label.setStyleSheet("color: white;")

        title_layout.addWidget(self.title_label)
        title_layout.addStretch()  # 添加弹性空间

        # 操作按钮区域（可选）
        button_layout = QHBoxLayout()

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedSize(80, 30)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #21618c;
            }
        """)
        refresh_btn.clicked.connect(self.on_refresh_clicked)

        button_layout.addWidget(refresh_btn)
        title_layout.addLayout(button_layout)

        layout.addWidget(title_frame)

    def setup_content_pages(self):
        """设置内容页面"""
        # 欢迎页面
        welcome_page = self.create_welcome_page()
        self.content_stack.addWidget(welcome_page)

        # 设备状态管理页面
        device_management_pages = {
            "topology_query": self.create_topology_query_page(),
            "performance_query": self.create_performance_query_page(),
            "process_query": self.create_process_query_page()
        }

        # 为每个二级菜单创建页面
        for page_name, page_widget in device_management_pages.items():
            self.content_stack.addWidget(page_widget)

        # 其他菜单的页面可以类似添加

    def create_welcome_page(self):
        """创建欢迎页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        # 欢迎标题
        welcome_title = QLabel("欢迎使用GAC诊断工具")
        welcome_title.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        welcome_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome_title)

        # 欢迎信息
        welcome_info = QLabel(
            "请从左侧菜单选择功能模块开始使用\n\n"
            "本系统支持以下功能：\n"
            "• 设备状态监控与管理\n"
            "• DTC故障诊断与分析\n"
            "• DID数据读取与写入\n"
            "• 文件传输与管理\n"
            "• 设备软件升级\n"
            "• 系统配置管理"
        )
        welcome_info.setFont(QFont("Microsoft YaHei", 12))
        welcome_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome_info)

        # 添加一些操作按钮
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)

        quick_connect_btn = QPushButton("快速连接设备")
        quick_connect_btn.setFixedSize(150, 40)
        quick_connect_btn.clicked.connect(self.on_quick_connect)

        button_layout.addWidget(quick_connect_btn)
        layout.addLayout(button_layout)

        return page

    def create_topology_query_page(self):
        """创建拓扑状态查询页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)

        # 页面标题
        page_title = QLabel("设备状态管理-拓扑状态查询")
        page_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(page_title)

        # 页面描述
        page_desc = QLabel("拓扑状态查询页面-显示设备连接拓扑和状态信息")
        page_desc.setFont(QFont("Microsoft YaHei", 10))
        page_desc.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(page_desc)

        # 添加分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #bdc3c7;")
        layout.addWidget(separator)

        # 拓扑显示区域（模拟）
        topology_area = QLabel("设备拓扑图显示区域\n\n"
                               "这里将显示设备的连接拓扑结构图，\n"
                               "包括各ECU节点的连接状态和通信关系。")
        topology_area.setAlignment(Qt.AlignCenter)
        topology_area.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                border: 1px dashed #bdc3c7;
                border-radius: 5px;
                padding: 50px;
                color: #7f8c8d;
            }
        """)
        topology_area.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(topology_area)

        # 操作按钮
        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新拓扑")
        refresh_btn.clicked.connect(lambda: self.refresh_topology())
        button_layout.addWidget(refresh_btn)

        export_btn = QPushButton("导出拓扑图")
        export_btn.clicked.connect(lambda: self.export_topology())
        button_layout.addWidget(export_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return page

    def create_performance_query_page(self):
        """创建性能状态查询页面"""
        page = QWidget()
        layout = QVBoxLayout(page)

        page_title = QLabel("设备状态管理-性能状态查询")
        page_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(page_title)

        # 模拟性能数据显示
        performance_info = QLabel("性能监控数据显示区域\n\n"
                                  "CPU使用率: --%\n"
                                  "内存使用率: --%\n"
                                  "网络流量: -- KB/s\n"
                                  "磁盘IO: -- MB/s")
        performance_info.setAlignment(Qt.AlignCenter)
        performance_info.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                border: 1px dashed #bdc3c7;
                border-radius: 5px;
                padding: 50px;
                color: #7f8c8d;
            }
        """)
        performance_info.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(performance_info)

        return page

    def create_process_query_page(self):
        """创建进程状态查询页面"""
        page = QWidget()
        layout = QVBoxLayout(page)

        page_title = QLabel("设备状态管理-进程状态查询")
        page_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(page_title)

        # 模拟进程列表显示
        process_info = QLabel("进程状态显示区域\n\n"
                              "进程ID | 进程名 | 状态 | CPU占用 | 内存占用\n"
                              "--------------------------------------------\n"
                              "数据加载中...")
        process_info.setAlignment(Qt.AlignCenter)
        process_info.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                border: 1px dashed #bdc3c7;
                border-radius: 5px;
                padding: 50px;
                color: #7f8c8d;
            }
        """)
        process_info.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(process_info)

        return page

    def setup_menu_bar(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu('文件')

        new_session = QAction('新建会话', self)
        new_session.setShortcut('Ctrl+N')
        file_menu.addAction(new_session)

        open_session = QAction('打开会话', self)
        open_session.setShortcut('Ctrl+O')
        file_menu.addAction(open_session)

        file_menu.addSeparator()

        exit_action = QAction('退出', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 视图菜单
        view_menu = menubar.addMenu('视图')

        # 工具菜单
        tool_menu = menubar.addMenu('工具')

        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_status_bar(self):
        """设置状态栏"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # 状态信息
        status_bar.showMessage("就绪")

        # 连接状态指示
        self.connection_status = QLabel("未连接设备")
        status_bar.addPermanentWidget(self.connection_status)

    def apply_styles(self):
        """应用样式表"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ecf0f1;
            }
            QStatusBar {
                background-color: #34495e;
                color: white;
            }
            QStatusBar::item {
                border: none;
            }
        """)

    def on_menu_item_clicked(self, item, column):
        """菜单项点击事件"""
        data = item.data(0, Qt.UserRole)

        if not data:
            return

        item_type = data.get("type")

        if item_type == "first":
            # 点击一级菜单，展开或收起二级菜单
            self.menu_tree.setCurrentItem(item)

        elif item_type == "second":
            # 点击二级菜单，切换内容页面
            first_key = data.get("first_key")
            second_key = data.get("second_key")

            self.current_first_level = first_key
            self.current_second_level = second_key

            # 更新标题
            first_text = item.parent().text(0)
            second_text = item.text(0)
            self.title_label.setText(f"{first_text}-{second_text}")

            # 切换内容页面（这里简化处理，实际应根据second_key切换）
            # 目前只实现了设备状态管理的三个页面
            if first_key == "device_management":
                if second_key == "topology_query":
                    self.content_stack.setCurrentIndex(1)
                elif second_key == "performance_query":
                    self.content_stack.setCurrentIndex(2)
                elif second_key == "process_query":
                    self.content_stack.setCurrentIndex(3)
                else:
                    self.content_stack.setCurrentIndex(0)  # 默认欢迎页面
            else:
                # 其他菜单的页面暂未实现，显示欢迎页面
                self.content_stack.setCurrentIndex(0)
                self.title_label.setText(f"{first_text}-{second_text}（功能开发中）")

            # 发射信号
            self.menu_item_selected.emit(first_key, second_key)

    def on_refresh_clicked(self):
        """刷新按钮点击事件"""
        QMessageBox.information(self, "刷新", "刷新功能将在后续实现")

    def on_quick_connect(self):
        """快速连接设备"""
        QMessageBox.information(self, "快速连接", "设备连接功能将在后续实现")

    def refresh_topology(self):
        """刷新拓扑图"""
        QMessageBox.information(self, "刷新拓扑", "拓扑刷新功能将在后续实现")

    def export_topology(self):
        """导出拓扑图"""
        QMessageBox.information(self, "导出拓扑", "拓扑导出功能将在后续实现")

    def show_about(self):
        """显示关于信息"""
        QMessageBox.about(self, "关于GAC诊断工具",
                          "GAC诊断工具 v1.0\n\n"
                          "基于PyQt5开发的汽车诊断工具\n"
                          "支持UDS协议、DoIP通信等诊断功能")

    def closeEvent(self, event):
        """关闭事件"""
        reply = QMessageBox.question(self, '确认退出',
                                     '确定要退出程序吗？',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()


# 应用程序入口
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 设置应用程序字体
    app.setFont(QFont("Microsoft YaHei", 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())