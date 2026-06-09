from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

from app.modules.app_config.controller.app_config_controller import AppConfigController
from app.presentation.views.welcome_view import WelcomeWidget
from app.common.ui.guide_overlay import GuideOverlay
from app.presentation.views.common_service_convert_dialog import CommonServiceConvertDialog
from app.presentation.views.dpt_convert_dialog import DPTConvertDialog


class MainView(QtWidgets.QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_controller = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("车载测试平台 v1.0 ")
        # 调整最小尺寸以适应 1080p @ 150% 缩放 (有效分辨率 1280x720)
        self.setMinimumSize(1024, 680)


        self.toolbar = QtWidgets.QToolBar("快速操作")
        self.toolbar.setIconSize(QtCore.QSize(20,20))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        self.toggle_nav_btn = QtWidgets.QToolButton()
        self.toggle_nav_btn.setText("☰")
        self.toggle_nav_btn.setToolTip("显示/隐藏功能导航")
        self.toggle_nav_btn.setCheckable(True)
        self.toggle_nav_btn.setChecked(True)
        self.toolbar.addWidget(self.toggle_nav_btn)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索功能...")
        self.search_edit.setMaximumWidth(280)
        self.toolbar.addWidget(self.search_edit)

        # Tools Button
        self.tools_btn = QtWidgets.QToolButton()
        self.tools_btn.setText("🛠️ 工具")
        self.tools_btn.setToolTip("实用工具箱")
        self.tools_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.tools_btn.setAutoRaise(True)
        self.tools_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.toolbar.addWidget(self.tools_btn)

        # Tools Menu
        tools_menu = QtWidgets.QMenu(self)
        dpt_action = QtWidgets.QAction("DPT文件转换", self)
        dpt_action.triggered.connect(self.show_dpt_convert_tool)
        tools_menu.addAction(dpt_action)

        common_service_action = QtWidgets.QAction("常用服务文件转换", self)
        common_service_action.triggered.connect(self.show_common_service_convert_tool)
        tools_menu.addAction(common_service_action)

        # --- 预留功能 (Marked for future dev) ---
        # 高级功能（脚本执行）
        script_exec_action = QtWidgets.QAction("脚本执行", self)
        script_exec_action.setEnabled(False) # 暂未开放
        tools_menu.addAction(script_exec_action)

        # 示例（示例页面）
        demo_page_action = QtWidgets.QAction("示例页面", self)
        demo_page_action.setEnabled(False) # 暂未开放
        tools_menu.addAction(demo_page_action)
        # ----------------------------------------

        self.tools_btn.setMenu(tools_menu)

        # 添加弹性空间，使“软件设置”按钮居右
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        self.settings_btn = QtWidgets.QToolButton()
        self.settings_btn.setText("软件设置")
        self.settings_btn.setToolTip("打开软件设置页面")
        self.settings_btn.setAutoRaise(True)
        self.settings_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.toolbar.addWidget(self.settings_btn)
        self.settings_btn.clicked.connect(self.show_settings_dialog)

        self.guide_btn = QtWidgets.QToolButton()
        self.guide_btn.setText("新手引导")
        self.guide_btn.setToolTip("查看功能指引")
        self.guide_btn.setAutoRaise(True)
        self.guide_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.toolbar.addWidget(self.guide_btn)
        self.guide_btn.clicked.connect(self.start_guide)

        # 搜索结果下拉列表
        self.search_result_list = QtWidgets.QListWidget()
        self.search_result_list.setWindowFlags(Qt.Popup)
        self.search_result_list.setFocusPolicy(Qt.NoFocus)
        self.search_result_list.setMouseTracking(True)
        self.search_result_list.setMaximumWidth(self.search_edit.maximumWidth())
        self.search_result_list.hide()
        # self.auth_label = QtWidgets.QLabel("✅ 已授权 (专业版)")
        # self.auth_label.setStyleSheet("color: #10B981; font-weight: 600; padding: 6px 12px; background-color: #ECFDF5; border-radius: 6px; border: 1px solid #D1FAE5;")
        # self.toolbar.addWidget(self.auth_label)
        self.nav_dock = QtWidgets.QDockWidget("功能导航", self)
        self.nav_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable)
        # 初始化最小宽度，防止过小
        self.nav_dock.setMinimumWidth(220)

        self.nav_tree = QtWidgets.QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setRootIsDecorated(True)
        self.nav_dock.setWidget(self.nav_tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.nav_dock)

        self.toggle_nav_btn.clicked.connect(self.nav_dock.setVisible)
        self.nav_dock.visibilityChanged.connect(self.toggle_nav_btn.setChecked)

        # Central Stacked Widget
        self.central_stack = QtWidgets.QStackedWidget()

        # 1. Welcome Page
        self.welcome_widget = WelcomeWidget()
        self.central_stack.addWidget(self.welcome_widget)

        # 2. Workspace (Tab Widget)
        self.workspace = QtWidgets.QTabWidget()
        self.workspace.setTabsClosable(True)
        self.workspace.setUsesScrollButtons(True)
        self.workspace.tabBar().setElideMode(Qt.ElideNone)

        self.workspace.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)

        self.central_stack.addWidget(self.workspace)

        self.setCentralWidget(self.central_stack)

        self.status_bar = QtWidgets.QStatusBar()

        # Desay Logo & IC_STH Text (最左边)
        logo_label = QtWidgets.QLabel()
        logo_path = "app/resources/images/desay_logo.jpg"
        logo_pixmap = QtGui.QPixmap(logo_path)
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaledToHeight(16, Qt.SmoothTransformation))
            logo_label.setContentsMargins(10, 0, 0, 0) # 左侧留点空隙

        text_label = QtWidgets.QLabel("2025 IC_STH PTV AT. All rights reserved.")
        text_label.setStyleSheet("color: #6B7280; font-weight: bold; font-family: 'Segoe UI', 'Microsoft YaHei UI'; margin-left: 5px; margin-right: 15px;")

        self.status_bar.addWidget(logo_label)
        self.status_bar.addWidget(text_label)

        self.doip_status_label = QtWidgets.QLabel("DoIP: ⏸️ 离线")
        self.ssh_status_label = QtWidgets.QLabel("SSH: ⏸️ 离线")
        self.someip_status_label = QtWidgets.QLabel("SOMEIP: ⏸️ 离线")

        # 初始状态设为灰色/离线
        for lbl in [self.doip_status_label, self.ssh_status_label, self.someip_status_label]:
            lbl.setStyleSheet("color: #6B7280;")

        self.status_bar.addPermanentWidget(self.doip_status_label)
        self.status_bar.addPermanentWidget(self.ssh_status_label)
        self.status_bar.addPermanentWidget(self.someip_status_label)
        self.status_bar.addPermanentWidget(QtWidgets.QLabel(" | "))
        self.performance_label = QtWidgets.QLabel("💻 CPU: -- | 内存: --")
        self.status_bar.addPermanentWidget(self.performance_label)
        self.setStatusBar(self.status_bar)

    def build_navigation(self, structure):
        self.nav_tree.clear()
        for category, data in structure.items():
            category_item = QtWidgets.QTreeWidgetItem(self.nav_tree)
            category_item.setText(0, category)
            category_item.setData(0, Qt.UserRole, "category")
            for child in data["children"]:
                child_item = QtWidgets.QTreeWidgetItem(category_item)
                child_item.setText(0, child)
                child_item.setData(0, Qt.UserRole, "function")
        self.nav_tree.expandAll()

    def show_search_results(self, items, pos=None):
        self.search_result_list.clear()
        if not items:
            self.search_result_list.hide()
            return
        self.search_result_list.addItems(items)
        self.search_result_list.setCurrentRow(0)
        if pos is None:
            pos = self.search_edit.mapToGlobal(self.search_edit.rect().bottomLeft())
        self.search_result_list.move(pos)
        self.search_result_list.resize(self.search_edit.width(), self.search_result_list.sizeHintForRow(0) * min(8, len(items)) + 2)
        self.search_result_list.show()

    def hide_search_results(self):
        self.search_result_list.hide()

    @QtCore.pyqtSlot(dict)
    def update_performance_summary(self, payload: dict):
        cpu = payload.get("cpu_percent")
        mem = payload.get("memory_usage")
        cpu_txt = f"{cpu:.0f}%" if isinstance(cpu, (int, float)) else "--"
        mem_txt = mem if isinstance(mem, str) else "--"
        self.performance_label.setText(f"💻 CPU: {cpu_txt} | 内存: {mem_txt}")

        protocol_status = payload.get("protocol_status", {})
        ssh_status = protocol_status.get("ssh", "离线")
        doip_status = protocol_status.get("doip", "离线")
        someip_status = protocol_status.get("someip", "离线")
        doip_device = protocol_status.get("doip_device")

        self.ssh_status_label.setText(f"SSH: {'✅' if ssh_status == '在线' else '⏸️'} {ssh_status}")
        self.ssh_status_label.setStyleSheet("color: #10B981;" if ssh_status == "在线" else "color: #6B7280;")

        if doip_status == "在线" and doip_device:
            self.doip_status_label.setText(f"DoIP (设备{doip_device}): ✅ 在线")
            self.doip_status_label.setStyleSheet("color: #10B981;")
        else:
            self.doip_status_label.setText("DoIP: ⏸️ 离线")
            self.doip_status_label.setStyleSheet("color: #6B7280;")

        self.someip_status_label.setText(f"SOMEIP: {'✅' if someip_status == '在线' else '⏸️'} {someip_status}")
        self.someip_status_label.setStyleSheet("color: #10B981;" if someip_status == "在线" else "color: #6B7280;")

    def show_settings_dialog(self, page_id: str | None = None, focus_target: str | None = None):
        if self.settings_controller is None:
            self.settings_controller = AppConfigController(self)
        if hasattr(self.settings_controller, "show_page"):
            self.settings_controller.show_page(page_id or "doip", focus_target=focus_target)
        else:
            self.settings_controller.view.show()
            self.settings_controller.view.raise_()
            self.settings_controller.view.activateWindow()

    def show_dpt_convert_tool(self):
        """显示DPT文件转换工具"""
        dialog = DPTConvertDialog(self)
        dialog.exec_()

    def show_common_service_convert_tool(self):
        """显示常用服务文件转换工具"""
        dialog = CommonServiceConvertDialog(self)
        dialog.exec_()

    def start_guide(self):
        if not hasattr(self, 'guide_overlay'):
            self.guide_overlay = GuideOverlay(self)

        self.guide_overlay.steps = [] # Clear previous steps
        self.guide_overlay.add_step(self.toggle_nav_btn, "导航切换", "点击此按钮可以展开或收起左侧的功能导航栏，提供更大的工作空间。")
        self.guide_overlay.add_step(self.search_edit, "全局搜索", "在这里输入关键词，可以快速查找并定位到需要的功能模块。")
        self.guide_overlay.add_step(self.nav_dock, "功能导航", "这里列出了所有的功能模块，可以点击展开查看详细的功能列表。")
        self.guide_overlay.add_step(self.workspace, "工作区域", "所有的功能页面都将在这里显示，支持多标签页操作，方便同时处理多个任务。")
        self.guide_overlay.add_step(self.settings_btn, "系统设置", "在这里可以配置软件的各项参数，包括连接设置、主题偏好等。")

        self.guide_overlay.start()

    def resizeEvent(self, event):
        """
        窗口调整大小时触发，用于自适应调整布局比例
        """
        super().resizeEvent(event) # 调用父类处理

        if hasattr(self, 'nav_dock'):
            window_width = self.width()

            # 设置导航栏宽度的动态约束
            # 最小宽度：220px (保证文字可读)
            # 最大宽度：窗口宽度的 30% (保证内容区域至少占 70%)
            min_width = 220
            max_width = int(window_width * 0.3)

            # 边界保护：确保 max >= min
            if max_width < min_width:
                max_width = min_width

            self.nav_dock.setMinimumWidth(min_width)
            self.nav_dock.setMaximumWidth(max_width)
