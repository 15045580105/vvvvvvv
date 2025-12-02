from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt

class MainView(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("车载诊断工具平台 v1.0 ")
        self.setMinimumSize(1400, 900)
        self.toolbar = QtWidgets.QToolBar("快速操作")
        self.toolbar.setIconSize(QtCore.QSize(20,20))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索功能...")
        self.search_edit.setMaximumWidth(280)
        self.toolbar.addWidget(self.search_edit)
        # 搜索结果下拉列表
        self.search_result_list = QtWidgets.QListWidget()
        self.search_result_list.setWindowFlags(QtCore.Qt.Popup)
        self.search_result_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self.search_result_list.setMouseTracking(True)
        self.search_result_list.setMaximumWidth(self.search_edit.maximumWidth())
        self.search_result_list.hide()
        # self.auth_label = QtWidgets.QLabel("✅ 已授权 (专业版)")
        # self.auth_label.setStyleSheet("color: #10B981; font-weight: 600; padding: 6px 12px; background-color: #ECFDF5; border-radius: 6px; border: 1px solid #D1FAE5;")
        # self.toolbar.addWidget(self.auth_label)
        self.nav_dock = QtWidgets.QDockWidget("功能导航", self)
        self.nav_tree = QtWidgets.QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setRootIsDecorated(True)
        self.nav_dock.setWidget(self.nav_tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.nav_dock)
        self.workspace = QtWidgets.QTabWidget()
        self.workspace.setTabsClosable(True)
        self.setCentralWidget(self.workspace)
        self.status_bar = QtWidgets.QStatusBar()
        self.status_bar.addPermanentWidget(QtWidgets.QLabel("DoIP: ✅ 在线"))
        self.status_bar.addPermanentWidget(QtWidgets.QLabel("SSH: ✅ 已连接"))
        self.status_bar.addPermanentWidget(QtWidgets.QLabel("SFTP: ⏸️ 离线"))
        self.status_bar.addPermanentWidget(QtWidgets.QLabel(" | "))
        self.status_bar.addPermanentWidget(QtWidgets.QLabel("💻 CPU: 12% | 内存: 2.3GB | 📡 3设备在线"))
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
