from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QStyle, QGroupBox, QSplitter,
    QMessageBox, QComboBox, QTextEdit
)
from app.presentation.views.base_view import BaseView
from app.common.ui.modern_widgets import MessageToast
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder


class SortableTreeWidgetItem(QTreeWidgetItem):
    """
    自定义 TreeWidgetItem，支持：
    1. 文件夹始终排在文件前面
    2. 数值列按数值大小排序（如文件大小）
    """
    def __lt__(self, other):
        tree = self.treeWidget()
        if not tree:
            return super().__lt__(other)

        column = tree.sortColumn()

        # 逻辑1: 文件夹始终在文件前面
        if column == 0:
            type1 = self.text(2)
            type2 = other.text(2)
            is_dir1 = (type1 == "文件夹")
            is_dir2 = (type2 == "文件夹")

            if is_dir1 != is_dir2:
                # 升序排序时，我们希望文件夹(True) 在 文件(False) 前面
                # 在 ascendingOrder (0->1) 中，需要 (0, 1) 或者 (True, False)?
                # return True < False -> False. So True comes after False?
                # Let's check:
                # If we return True, self < other. Self comes first in Ascending.
                # If is_dir1 (Folder) and is_dir2 (File). We want Folder < File.
                # return True (if Logic says Folder < File).
                return is_dir1

            return self.text(0).lower() < other.text(0).lower()

        # 逻辑2: 大小列 (col 3) 按数值排序
        if column == 3:
            return self._parse_size(self.text(3)) < self._parse_size(other.text(3))

        return super().__lt__(other)

    def _parse_size(self, size_str):
        if not size_str: return -1
        parts = size_str.split()
        if len(parts) != 2: return 0
        try:
            val = float(parts[0])
            unit = parts[1].upper()
            multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4, 'PB': 1024**5}
            return val * multipliers.get(unit, 1)
        except:
            return 0


class FileTransferView(BaseView):
    # 信号定义

    # 本地文件信号
    refresh_local_requested = pyqtSignal()
    local_path_entered = pyqtSignal(str)
    local_item_expanded = pyqtSignal(str)
    local_item_clicked = pyqtSignal(str)
    go_up_local_requested = pyqtSignal()
    browse_local_requested = pyqtSignal()

    # 远程文件信号
    refresh_remote_requested = pyqtSignal()
    remote_path_entered = pyqtSignal(str)
    remote_item_expanded = pyqtSignal(str)
    remote_item_clicked = pyqtSignal(str)
    go_up_remote_requested = pyqtSignal()

    # 传输信号
    upload_requested = pyqtSignal()
    download_requested = pyqtSignal()

    # 设备信号
    # device_selected = pyqtSignal(dict) # Select device from combo

    def setup_ui(self):
        # 使用垂直布局
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # === 1. 构建主分割器 ===
        main_splitter = QSplitter(Qt.Vertical)

        # --- 上半部分：左右两栏 ---
        top_splitter = QSplitter(Qt.Horizontal)

        # 左侧：本地文件
        left_group = QGroupBox("本地文件")
        left_layout = QVBoxLayout(left_group)

        # 路径行
        local_path_layout = QHBoxLayout()
        local_path_label = QLabel("路径:")
        self.local_path_edit = QLineEdit()
        local_up_btn = QPushButton("↑")
        local_up_btn.setMaximumWidth(30)
        local_browse_btn = QPushButton("浏览")
        local_refresh_btn = QPushButton("刷新")

        local_path_layout.addWidget(local_path_label)
        local_path_layout.addWidget(self.local_path_edit)
        local_path_layout.addWidget(local_up_btn)
        local_path_layout.addWidget(local_browse_btn)
        local_path_layout.addWidget(local_refresh_btn)
        left_layout.addLayout(local_path_layout)

        # 本地树
        self.local_tree = QTreeWidget()
        self._setup_tree_widget(self.local_tree, ["名称", "修改日期", "类型", "大小"], [220, 130, 70, 100])
        self.local_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        left_layout.addWidget(self.local_tree)

        # 连接本地信号
        local_up_btn.clicked.connect(self.go_up_local_requested.emit)
        local_browse_btn.clicked.connect(self.browse_local_requested.emit)
        local_refresh_btn.clicked.connect(self.refresh_local_requested.emit)
        self.local_path_edit.returnPressed.connect(lambda: self.local_path_entered.emit(self.local_path_edit.text()))
        self.local_tree.itemExpanded.connect(self._on_local_item_expanded)
        self.local_tree.itemClicked.connect(self._on_local_item_clicked)
        self.local_tree.setExpandsOnDoubleClick(True)

        # 中间：操作按钮
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignCenter)
        upload_btn = QPushButton("↑ 上传")
        upload_btn.setStyleSheet("background-color: #28a745; color: white; border-radius: 4px; padding: 6px;")
        download_btn = QPushButton("↓ 下载")
        download_btn.setStyleSheet("background-color: #ffc107; color: black; border-radius: 4px; padding: 6px;")
        center_layout.addWidget(upload_btn)
        center_layout.addWidget(download_btn)
        center_widget.setMaximumWidth(80)

        upload_btn.clicked.connect(self.upload_requested.emit)
        download_btn.clicked.connect(self.download_requested.emit)

        # 右侧：远程文件
        right_group = QGroupBox("远程设备文件")
        right_layout = QVBoxLayout(right_group)

        # controls layout (grid for alignment)
        remote_controls_layout = QtWidgets.QGridLayout()
        # remote_controls_layout.setContentsMargins(0, 0, 0, 0)

        # Row 1: Device Selection
        device_label = QLabel("设备:")
        self.device_combo = QComboBox()
        # Make combo expand
        self.device_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        remote_controls_layout.addWidget(device_label, 0, 0)
        remote_controls_layout.addWidget(self.device_combo, 0, 1, 1, 3) # Span 3 columns

        # Row 2: Path Navigation
        remote_path_label = QLabel("路径:")
        self.remote_path_edit = QLineEdit()
        remote_up_btn = QPushButton("↑")
        remote_up_btn.setMaximumWidth(30)
        self.remote_refresh_btn = QPushButton("刷新")

        remote_controls_layout.addWidget(remote_path_label, 1, 0)
        remote_controls_layout.addWidget(self.remote_path_edit, 1, 1)
        remote_controls_layout.addWidget(remote_up_btn, 1, 2)
        remote_controls_layout.addWidget(self.remote_refresh_btn, 1, 3)

        remote_controls_layout.setColumnStretch(1, 1) # Make input column expand

        right_layout.addLayout(remote_controls_layout)

        # 远程树
        self.remote_tree = QTreeWidget()
        self._setup_tree_widget(self.remote_tree, ["名称", "修改日期", "类型", "大小"], [220, 130, 70, 100])
        self.remote_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        right_layout.addWidget(self.remote_tree)

        # 连接远程信号
        remote_up_btn.clicked.connect(self.go_up_remote_requested.emit)
        self.remote_refresh_btn.clicked.connect(self.refresh_remote_requested.emit)
        self.remote_path_edit.returnPressed.connect(lambda: self.remote_path_entered.emit(self.remote_path_edit.text()))
        self.remote_tree.itemExpanded.connect(self._on_remote_item_expanded)
        self.remote_tree.itemClicked.connect(self._on_remote_item_clicked)
        self.remote_tree.setExpandsOnDoubleClick(True)

        top_splitter.addWidget(left_group)
        top_splitter.addWidget(center_widget)
        top_splitter.addWidget(right_group)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 0)
        top_splitter.setStretchFactor(2, 1)
        # Ensure left and right panels have equal initial width, and center button area is fixed
        top_splitter.setCollapsible(0, False)
        top_splitter.setCollapsible(2, False)
        top_splitter.setSizes([600, 80, 600])

        # --- 下半部分：传输日志 ---
        bottom_group = QGroupBox("操作日志")
        bottom_layout = QVBoxLayout(bottom_group)
        self.transfer_log = QTextEdit()
        self.transfer_log.setReadOnly(True)
        LogPanelBuilder.attach_search(bottom_layout, self.transfer_log)
        bottom_layout.addWidget(self.transfer_log)

        self.main_splitter = LogAreaSplitter(self, min_log_height=150, max_log_ratio=0.8)
        self.main_splitter.set_panels(top_splitter, bottom_group, initial_log_height=120)

        outer_layout.addWidget(self.main_splitter)

        # 初始化图标
        self.folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

    def _setup_tree_widget(self, tree_widget, headers, column_widths):
        tree_widget.setHeaderLabels(headers)
        header = tree_widget.header()
        for i, width in enumerate(column_widths):
            header.resizeSection(i, width)
        tree_widget.setSortingEnabled(True)

    def _on_local_item_expanded(self, item):
        path = item.data(0, Qt.UserRole)
        self.local_item_expanded.emit(path)

    def _on_remote_item_expanded(self, item):
        path = item.data(0, Qt.UserRole)
        self.remote_item_expanded.emit(path)

    def _on_local_item_clicked(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path:
            self.local_path_edit.setText(path)
            self.local_item_clicked.emit(path)

    def _on_remote_item_clicked(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path:
            self.remote_path_edit.setText(path)
            self.remote_item_clicked.emit(path)

    def set_local_roots(self, roots): # Update
        self.local_tree.clear()
        for root in roots:
            item = SortableTreeWidgetItem(self.local_tree)
            item.setText(0, root)
            item.setText(2, "磁盘" if ":" in root else "根目录")
            item.setIcon(0, self.folder_icon)
            item.setData(0, Qt.UserRole, root)
            # 添加一个空子节点以显示展开图标（实现懒加载）
            dummy = QTreeWidgetItem(item)
            dummy.setText(0, "Loading...")

    def set_remote_root(self, path):
        """设置远程文件树的根节点"""
        self.remote_tree.clear()

        # 确定显示名称
        path = path.replace('\\', '/')
        if path == '/' or path == '':
            display_name = '/'
            full_path = '/'
        else:
            path = path.rstrip('/')
            display_name = path.split('/')[-1] # basename
            full_path = path

        item = SortableTreeWidgetItem(self.remote_tree)
        item.setText(0, display_name)
        item.setText(2, "文件夹")
        item.setIcon(0, self.folder_icon)
        item.setData(0, Qt.UserRole, full_path)

        # 默认展开根节点
        item.setExpanded(True)
        # 添加 dummy 以防万一，虽然我们会马上填充
        QTreeWidgetItem(item)

    def update_node_children(self, path, items, is_remote=False): # Update
        tree = self.remote_tree if is_remote else self.local_tree

        # 查找对应路径的节点
        target_item = None

        # 特殊情况：如果是Windows盘符，需要匹配 root items
        # 或者如果是 Linux 根如果 path == "/"

        # 遍历查找。为了简化，这里可以优化为维护一个 map，但遍历也行
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            item_path = item.data(0, Qt.UserRole)
            if item_path == path: # 注意路径格式匹配
                target_item = item
                break
            # 兼容 Windows 盘符 C: vs C:\
            if item_path and path and item_path.rstrip('\\/') == path.rstrip('\\/'):
                 target_item = item
                 break
            iterator += 1

        if not target_item:
            # 没找到节点
            return False

        # 清除现有子节点 (dummy node)
        target_item.takeChildren()

        for name, mtime, ftype, size in items:
            child = SortableTreeWidgetItem(target_item)
            child.setText(0, name)
            child.setText(1, mtime)
            child.setText(2, ftype)
            child.setText(3, size)

            # 构建完整路径
            if path.endswith(('/', '\\')):
                full_path = path + name
            else:
                full_path = path + '/' + name # 简单拼接，controller负责正确性
                if '\\' in path: # Windows style
                     full_path = path + '\\' + name

            child.setData(0, Qt.UserRole, full_path)

            if ftype == "文件夹":
                child.setIcon(0, self.folder_icon)
                # 添加 dummy 节点以允许展开
                QTreeWidgetItem(child)
            else:
                child.setIcon(0, self.file_icon)

        return True

    def expand_local_item(self, path):
         # logic to find and expand item
         pass

    def select_local_item(self, path):
        pass

    def append_log(self, message):
        self.transfer_log.append(f"[{QtCore.QTime.currentTime().toString()}] {message}")

    def show_toast(self, message, message_type=1): # Default to Error (1) as requested context implies "Not Connected"
        # But generic usage might be Info.
        # User said "Show toast if not connected".
        # Let's default to Info (2) or make it explicit.
        # ModernWidgets MessageToast: 0=Success, 1=Error, else=Info.
        toast = MessageToast(self)
        toast.show_toast(message, message_type)

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def show_info(self, title, message):
        QMessageBox.information(self, title, message)

    # Helper for device combo
    def get_selected_device(self):
        return self.device_combo.currentData()
