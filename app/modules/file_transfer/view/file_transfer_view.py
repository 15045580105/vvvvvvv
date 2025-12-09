from PyQt5 import QtWidgets, QtCore

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

# Qt orientation compatibility constants
QT_HORIZONTAL = getattr(QtCore.Qt, "Horizontal", 1)
QT_VERTICAL = getattr(QtCore.Qt, "Vertical", 2)
ALIGN_CENTER = int(getattr(QtCore.Qt, "AlignCenter", 132))
USER_ROLE = int(getattr(QtCore.Qt, "UserRole", 32))
SP_DIR_ICON = getattr(QtWidgets.QStyle, "SP_DirIcon", 2)
SP_FILE_ICON = getattr(QtWidgets.QStyle, "SP_FileIcon", 3)


class FileTransferView(BaseView):
    # 向外暴露的信号，由 Controller 连接处理
    local_browse_clicked = QtCore.pyqtSignal()
    local_refresh_clicked = QtCore.pyqtSignal(str)
    local_path_edited = QtCore.pyqtSignal(str)
    local_dir_expanded = QtCore.pyqtSignal(str)

    # 远程树相关信号
    remote_refresh_clicked = QtCore.pyqtSignal()
    remote_filter_changed = QtCore.pyqtSignal(str)
    remote_dir_expanded = QtCore.pyqtSignal(str)

    def setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(8)

        # ---------------- 本地文件面板 ----------------
        local_panel = QtWidgets.QGroupBox("本地文件")
        local_layout = QtWidgets.QVBoxLayout()

        # 顶部路径行：标签 + 路径编辑框 + 浏览按钮 + 刷新按钮
        local_header = QtWidgets.QHBoxLayout()
        local_header.addWidget(QtWidgets.QLabel("📁 路径:"))

        self.local_path = QtWidgets.QLineEdit("C:/Diagnostics/Logs")
        local_header.addWidget(self.local_path)

        self.browse_local_btn = ModernButton("浏览...", "#0EA5E9", "📂")
        local_header.addWidget(self.browse_local_btn)

        self.local_refresh_btn = ModernButton("刷新", "#0EA5E9", "🔄")
        local_header.addWidget(self.local_refresh_btn)

        local_layout.addLayout(local_header)

        # 本地目录树
        self.local_tree = QtWidgets.QTreeWidget()
        self.local_tree.setHeaderLabels(["名称", "大小", "修改时间"])
        self.local_tree.setColumnCount(3)
        self.local_tree.setAlternatingRowColors(True)
        self.local_tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.local_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.local_tree.setAllColumnsShowFocus(True)
        # 让名称列自动拉伸，保证能看清文件名
        lh = self.local_tree.header()
        lh.setStretchLastSection(False)
        lh.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)   # 名称
        lh.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)  # 大小
        lh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)  # 修改时间
        local_layout.addWidget(self.local_tree)

        local_panel.setLayout(local_layout)

        # ---------------- 中间按钮面板（上传/下载） ----------------
        btn_panel = QtWidgets.QVBoxLayout()
        btn_panel.setSpacing(14)
        btn_panel.setContentsMargins(0, 0, 0, 0)
        btn_panel.addStretch(1)

        # 上传按钮居中
        self.upload_btn = TableButton("上传", "#059669", "➡")
        self.upload_btn.setFixedWidth(120)
        upload_row = QtWidgets.QHBoxLayout()
        upload_row.setSpacing(0)
        upload_row.addStretch(1)
        upload_row.addWidget(self.upload_btn)
        upload_row.addStretch(1)
        btn_panel.addLayout(upload_row)

        # 下载按钮居中
        self.download_btn = TableButton("下载", "#F59E0B", "⬅")
        self.download_btn.setFixedWidth(120)
        download_row = QtWidgets.QHBoxLayout()
        download_row.setSpacing(0)
        download_row.addStretch(1)
        download_row.addWidget(self.download_btn)
        download_row.addStretch(1)
        btn_panel.addLayout(download_row)

        btn_panel.addStretch(1)

        # ---------------- 远程文件面板 ----------------
        remote_panel = QtWidgets.QGroupBox("远程设备文件 (/log)")
        remote_layout = QtWidgets.QVBoxLayout()

        remote_header = QtWidgets.QHBoxLayout()
        remote_header.addWidget(QtWidgets.QLabel("🔍 搜索:"))
        self.remote_filter = QtWidgets.QLineEdit()
        self.remote_filter.setPlaceholderText("APPID或路径...")
        remote_header.addWidget(self.remote_filter)
        self.remote_refresh_btn = ModernButton("刷新", "#0EA5E9", "🔄")
        remote_header.addWidget(self.remote_refresh_btn)

        remote_layout.addLayout(remote_header)

        # 远程目录树：仿资源管理器左侧，仅一列名称，无表头
        self.remote_tree = QtWidgets.QTreeWidget()
        self.remote_tree.setColumnCount(1)
        self.remote_tree.setHeaderHidden(True)
        self.remote_tree.setAlternatingRowColors(True)
        self.remote_tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.remote_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.remote_tree.setAllColumnsShowFocus(True)
        # 让这一列随面板自动撑满，避免名称太窄
        self.remote_tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        remote_layout.addWidget(self.remote_tree)

        remote_panel.setLayout(remote_layout)

        # ---------------- 任务队列表格 ----------------
        task_panel = QtWidgets.QGroupBox("传输任务队列")
        task_layout = QtWidgets.QVBoxLayout()

        self.task_table = QtWidgets.QTableWidget(0, 4)
        self.task_table.setHorizontalHeaderLabels(["文件名", "进度", "状态", "操作"])

        # 优化任务表格视觉与行为
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setAlternatingRowColors(True)
        self.task_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.task_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.task_table.setWordWrap(False)

        vh = self.task_table.verticalHeader()
        vh.setDefaultSectionSize(42)
        vh.setMinimumSectionSize(38)

        hh = self.task_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)  # 文件名
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)    # 进度
        self.task_table.setColumnWidth(1, 180)
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)  # 状态
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)    # 操作
        self.task_table.setColumnWidth(3, 150)

        task_layout.addWidget(self.task_table)
        task_panel.setLayout(task_layout)

        # ---------------- 顶部文件区与底部任务区分隔 ----------------
        file_splitter = QtWidgets.QSplitter(QT_HORIZONTAL)
        file_splitter.addWidget(local_panel)

        btn_widget = QtWidgets.QWidget()
        btn_widget.setLayout(btn_panel)
        btn_widget.setMaximumWidth(170)
        file_splitter.addWidget(btn_widget)

        file_splitter.addWidget(remote_panel)
        file_splitter.setSizes([380, 140, 420])

        main_splitter = QtWidgets.QSplitter(QT_VERTICAL)
        main_splitter.addWidget(file_splitter)
        main_splitter.addWidget(task_panel)
        main_splitter.setSizes([560, 180])

        layout.addWidget(main_splitter)

        # 初始初始化进度条引用存储
        self._task_progress_bars = {}

        # 本地目录浏览相关初始化（不再直接访问文件系统）
        self._local_root_path = self.local_path.text().strip()

        # 本地：仅发出信号，具体业务逻辑由 Controller 处理
        self.browse_local_btn.clicked.connect(self._emit_local_browse)
        self.local_refresh_btn.clicked.connect(self._emit_local_refresh)
        self.local_path.editingFinished.connect(self._emit_local_path_edited)
        self.local_tree.itemExpanded.connect(self._emit_local_item_expanded)

        # 远程：仅发出信号
        self.remote_refresh_btn.clicked.connect(self._emit_remote_refresh)
        self.remote_filter.textChanged.connect(self._emit_remote_filter_changed)
        self.remote_tree.itemExpanded.connect(self._emit_remote_item_expanded)

    # --- 向 Controller 发信号的包装槽（本地） ---
    def _emit_local_browse(self):
        self.local_browse_clicked.emit()

    def _emit_local_refresh(self):
        path = self.local_path.text().strip()
        if not path:
            return
        self.local_refresh_clicked.emit(path)

    def _emit_local_path_edited(self):
        path = self.local_path.text().strip()
        if not path:
            return
        self.local_path_edited.emit(path)

    def _emit_local_item_expanded(self, item):
        if not item:
            return
        path = item.data(0, USER_ROLE)
        if not path:
            return
        self.local_dir_expanded.emit(path)

    # --- 向 Controller 发信号的包装槽（远程） ---
    def _emit_remote_refresh(self):
        self.remote_refresh_clicked.emit()

    def _emit_remote_filter_changed(self, text: str):
        self.remote_filter_changed.emit(text.strip())

    def _emit_remote_item_expanded(self, item):
        if not item:
            return
        path = item.data(0, USER_ROLE)
        if not path:
            return
        self.remote_dir_expanded.emit(path)

    # --- View 只负责根据数据渲染，不做文件访问 ---
    def render_local_tree(self, root_name: str, root_path: str):
        """构造本地根节点，并为其添加占位子节点，便于后续展开加载。"""
        self.local_tree.clear()
        root_item = QtWidgets.QTreeWidgetItem([root_name, "", ""])
        root_item.setData(0, USER_ROLE, root_path)
        root_item.setData(0, USER_ROLE + 1, True)
        icon_provider = QtWidgets.QFileIconProvider()
        root_item.setIcon(0, icon_provider.icon(QtWidgets.QFileIconProvider.Folder))
        # 添加一个占位子节点，表示“可展开”
        placeholder = QtWidgets.QTreeWidgetItem(["加载中...", "", ""])
        root_item.addChild(placeholder)
        self.local_tree.addTopLevelItem(root_item)

    def render_local_children(self, parent_path: str, children: list):
        """根据 Controller 提供的数据填充本地树某个节点的子节点。

        children: List[{
            'name': str,
            'path': str,
            'is_dir': bool,
            'size': Optional[str],
            'mtime': Optional[str],
        }]
        """
        def find_item(root_item, target_path):
            if root_item.data(0, USER_ROLE) == target_path:
                return root_item
            for i in range(root_item.childCount()):
                found = find_item(root_item.child(i), target_path)
                if found:
                    return found
            return None

        if self.local_tree.topLevelItemCount() == 0:
            return
        root_item = self.local_tree.topLevelItem(0)
        parent_item = find_item(root_item, parent_path)
        if parent_item is None:
            return

        # 清空原有子节点（包括占位）
        parent_item.takeChildren()
        icon_provider = QtWidgets.QFileIconProvider()
        for info in children:
            cols = [info["name"], info.get("size") or "", info.get("mtime") or ""]
            item = QtWidgets.QTreeWidgetItem(cols)
            item.setData(0, USER_ROLE, info["path"])
            item.setData(0, USER_ROLE + 1, bool(info.get("is_dir")))
            if info.get("is_dir"):
                item.setIcon(0, icon_provider.icon(QtWidgets.QFileIconProvider.Folder))
                # 目录也预先挂一个占位子节点，表示后面还能展开
                placeholder = QtWidgets.QTreeWidgetItem(["加载中...", "", ""])
                item.addChild(placeholder)
            else:
                item.setIcon(0, icon_provider.icon(QtWidgets.QFileIconProvider.File))
            parent_item.addChild(item)

    def render_remote_tree(self, root_name: str, root_path: str):
        """根据 Controller 提供的远程根路径信息，构造远程根节点。

        远程树只显示名称一列，样式类似资源管理器左侧导航树。
        """
        self.remote_tree.clear()
        root_item = QtWidgets.QTreeWidgetItem([root_name])
        root_item.setData(0, USER_ROLE, root_path)
        root_item.setData(0, USER_ROLE + 1, True)  # is_dir
        style = self.style()
        icon = style.standardIcon(SP_DIR_ICON)
        root_item.setIcon(0, icon)
        self.remote_tree.addTopLevelItem(root_item)
        self.remote_tree.expandItem(root_item)

    def render_remote_children(self, parent_path: str, children: list):
        """根据 Controller 提供的远程子节点数据，填充到 parent 对应的节点下。

        children: List[{
            'name': str,
            'path': str,        # 完整远程路径，如 /log/app1/2025/11/log.txt
            'is_dir': bool,
            'appid': str | None,
            'size_kb': str | None,
            'ctime': str | None,
            'mtime': str | None,
        }]

        除名称和图标外的 APPID/大小/时间信息，不在树上占列，只作为 tooltip 提示。
        """
        def find_item(root_item, target_path):
            if root_item.data(0, USER_ROLE) == target_path:
                return root_item
            for i in range(root_item.childCount()):
                found = find_item(root_item.child(i), target_path)
                if found:
                    return found
            return None

        if self.remote_tree.topLevelItemCount() == 0:
            return
        root_item = self.remote_tree.topLevelItem(0)
        parent_item = find_item(root_item, parent_path)
        if parent_item is None:
            return

        parent_item.takeChildren()
        style = self.style()
        dir_icon = style.standardIcon(SP_DIR_ICON)
        file_icon = style.standardIcon(SP_FILE_ICON)

        for info in children:
            # 只显示名称，其他信息放 tooltip
            item = QtWidgets.QTreeWidgetItem([info["name"]])
            item.setData(0, USER_ROLE, info["path"])
            item.setData(0, USER_ROLE + 1, bool(info.get("is_dir")))

            # 拼接 tooltip 文本
            tooltip_parts = []
            if info.get("appid"):
                tooltip_parts.append(f"APPID: {info['appid']}")
            if info.get("size_kb"):
                tooltip_parts.append(f"大小: {info['size_kb']} KB")
            if info.get("ctime"):
                tooltip_parts.append(f"创建时间: {info['ctime']}")
            if info.get("mtime"):
                tooltip_parts.append(f"修改时间: {info['mtime']}")
            if tooltip_parts:
                item.setToolTip(0, "\n".join(tooltip_parts))

            if info.get("is_dir"):
                item.setIcon(0, dir_icon)
            else:
                item.setIcon(0, file_icon)
            parent_item.addChild(item)

    # --- Helper methods for task table ---
    def populate_tasks(self, tasks):
        """tasks: List[Dict{name:str, progress:int, status:str}]"""
        # 清空旧引用
        self._task_progress_bars.clear()
        self.task_table.setRowCount(len(tasks))
        for row, t in enumerate(tasks):
            # 文件名
            name_item = QtWidgets.QTableWidgetItem(t.get("name", ""))
            name_item.setToolTip(t.get("name", ""))
            self.task_table.setItem(row, 0, name_item)
            # 进度（进度条 + 取消按钮）
            progress_widget = QtWidgets.QWidget()
            pw_layout = QtWidgets.QHBoxLayout(progress_widget)
            pw_layout.setContentsMargins(6, 4, 6, 4)
            pw_layout.setSpacing(8)
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(t.get("progress", 0)))
            bar.setFormat(f"{int(t.get('progress', 0))}%")
            bar.setTextVisible(True)
            bar.setMinimumWidth(110)
            pw_layout.addWidget(bar)
            cancel_btn = TableButton("取消", "#EF4444", "✕")
            cancel_btn.setFixedWidth(50)
            pw_layout.addWidget(cancel_btn)
            pw_layout.addStretch(1)
            self.task_table.setCellWidget(row, 1, progress_widget)
            # 状态
            status_item = QtWidgets.QTableWidgetItem(t.get("status", "等待"))
            status_item.setTextAlignment(ALIGN_CENTER)
            self.task_table.setItem(row, 2, status_item)
            # 操作（重试 / 删除）
            action_widget = QtWidgets.QWidget()
            aw_layout = QtWidgets.QHBoxLayout(action_widget)
            aw_layout.setContentsMargins(6, 4, 6, 4)
            aw_layout.setSpacing(8)
            retry_btn = TableButton("重试", "#0EA5E9", "🔄")
            retry_btn.setFixedWidth(60)
            delete_btn = TableButton("删除", "#6B7280", "🗑")
            delete_btn.setFixedWidth(60)
            aw_layout.addStretch(1)
            aw_layout.addWidget(retry_btn)
            aw_layout.addWidget(delete_btn)
            aw_layout.addStretch(1)
            self.task_table.setCellWidget(row, 3, action_widget)
            # 存储进度条引用
            self._task_progress_bars[row] = bar

    def update_task_progress(self, row: int, progress: int):
        if row not in self._task_progress_bars:
            return
        bar = self._task_progress_bars[row]
        clamped = max(0, min(100, int(progress)))
        bar.setValue(clamped)
        bar.setFormat(f"{clamped}%")
        status_item = self.task_table.item(row, 2)
        if status_item:
            status_item.setText("完成" if clamped >= 100 else "进行中")

    # --- 通用对话框封装，供 Controller 使用 ---
    def get_file_dialog(self, parent=None) -> QtWidgets.QFileDialog:
        """提供一个统一配置的 QFileDialog，便于 Controller 调用。

        当前主要用于选择本地目录，Controller 可以根据需要调整 fileMode/filters。
        """
        dlg_parent = parent or self
        dialog = QtWidgets.QFileDialog(dlg_parent)
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
        return dialog


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = FileTransferView()
    view.setup_ui()
    view.show()
    app.exec_()
