import os
import stat
import datetime
from app.core.base_controller import BaseController
from app.modules.file_transfer.model.file_transfer_model import FileTransferModel
from app.modules.file_transfer.view.file_transfer_view import FileTransferView
from app.services.file_manage.file_transfer_service import FileTransferService
from app.services.system.config_service import ConfigService


class FileTransferController(BaseController):
    def __init__(self, parent=None):
        self.model = FileTransferModel(parent)
        self.view = FileTransferView(parent)
        super().__init__(self.model, self.view, parent)

        self.config_service = ConfigService()
        # 初始化文件传输服务
        self.file_transfer_service = FileTransferService()

        # 连接 View 信号到 Controller 槽，实现严格 MVC
        self.view.local_browse_clicked.connect(self.on_local_browse_clicked)
        self.view.local_refresh_clicked.connect(self.on_local_refresh_clicked)
        self.view.local_path_edited.connect(self.on_local_path_edited)
        self.view.local_dir_expanded.connect(self.on_local_dir_expanded)

        # 远程树相关
        self.view.remote_refresh_clicked.connect(self.on_remote_refresh_clicked)
        self.view.remote_filter_changed.connect(self.on_remote_filter_changed)
        self.view.remote_dir_expanded.connect(self.on_remote_dir_expanded)

        # 初始化本地目录树
        self._init_local_tree()
        # 初始化设备列表
        self._init_device_list()
        # 初始化远程树（根节点）
        self._init_remote_tree_root()

    def _init_device_list(self):
        """加载已配置的设备列表到下拉框"""
        self.view.device_combo.clear()
        devices = self.config_service.load_devices() or []
        for dev in devices:
            display = f"{dev.get('name', 'Unknown')} ({dev.get('ip', '')})"
            self.view.device_combo.addItem(display, dev)

    def _init_remote_tree_root(self):
        """初始化远程树显示"""
        self.view.remote_tree.clear()

    def get_view(self):
        return self.view

    # --- 本地文件树相关业务逻辑（Controller 层） ---
    def _init_local_tree(self):
        path = self.model.local_path
        if not os.path.isdir(path):
            return
        root_name = os.path.basename(path.rstrip(os.sep)) or path
        self.view.local_path.setText(path)
        self.view.render_local_tree(root_name, path)
        # 首次加载根目录子级
        self._populate_children(path)

    def on_local_browse_clicked(self):
        start_dir = self.view.local_path.text().strip() or os.path.expanduser("~")
        dialog = self.view.get_file_dialog(self.view)
        dialog.setFileMode(dialog.Directory)
        dialog.setOption(dialog.ShowDirsOnly, True)
        dialog.setDirectory(start_dir)
        if dialog.exec_() != dialog.Accepted:
            return
        selected = dialog.selectedFiles()
        if not selected:
            return
        path = selected[0]
        if not os.path.isdir(path):
            return
        self.model.local_path = path
        root_name = os.path.basename(path.rstrip(os.sep)) or path
        self.view.local_path.setText(path)
        self.view.render_local_tree(root_name, path)
        self._populate_children(path)

    def on_local_refresh_clicked(self, path: str):
        if not os.path.isdir(path):
            return
        self.model.local_path = path
        root_name = os.path.basename(path.rstrip(os.sep)) or path
        self.view.render_local_tree(root_name, path)
        self._populate_children(path)

    def on_local_path_edited(self, path: str):
        if not os.path.isdir(path):
            # 简单失败处理：还原为 model 中的路径
            self.view.local_path.setText(self.model.local_path)
            return
        self.model.local_path = path
        root_name = os.path.basename(path.rstrip(os.sep)) or path
        self.view.render_local_tree(root_name, path)
        self._populate_children(path)

    def on_local_dir_expanded(self, path: str):
        if not os.path.isdir(path):
            return
        self._populate_children(path)

    def _populate_children(self, dir_path: str):
        """扫描一个目录，生成视图所需的数据结构，并驱动 View 渲染。"""
        try:
            entries = list(os.scandir(dir_path))
        except OSError:
            return

        dirs = sorted([e for e in entries if e.is_dir(follow_symlinks=False)], key=lambda e: e.name.lower())
        files = sorted([e for e in entries if e.is_file(follow_symlinks=False)], key=lambda e: e.name.lower())

        children = []
        for entry in dirs:
            children.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": True,
                "size": "",
                "mtime": "",
            })
        for entry in files:
            try:
                st = entry.stat()
            except OSError:
                continue
            children.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": False,
                "size": self._format_size(st.st_size),
                "mtime": self._format_mtime(st.st_mtime),
            })

        self.view.render_local_children(dir_path, children)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    @staticmethod
    def _format_mtime(timestamp: float) -> str:
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return ""

    # --- 远程文件树相关业务逻辑 ---

    def on_remote_refresh_clicked(self):
        """远程刷新按钮点击：连接设备并刷新根目录"""
        idx = self.view.device_combo.currentIndex()
        if idx < 0:
            return

        device = self.view.device_combo.itemData(idx)
        if not device:
            return

        # 尝试连接
        success = self.file_transfer_service.connect_device(
            hostname=device.get('ip'),
            port=int(device.get('port', 22)),
            username=device.get('user', 'root'),
            password=device.get('password')
        )

        if success:
            root_path = "/log"
            self.view.render_remote_tree("log", root_path)
            self._fetch_and_render_remote(root_path)
        else:
            # TODO: Show error
            print("Connection failed")

    def on_remote_filter_changed(self, text: str):
        # 暂时只支持过滤当前显示的视图，或者需要在搜索时遍历整个树？
        # 既然是懒加载，本地过滤只能过滤已加载的。
        # 这里简化处理：不做任何事，或者简单过滤当前层级
        pass

    def on_remote_dir_expanded(self, path: str):
        """远程目录节点展开时，填充其子节点。"""
        if not self.file_transfer_service.is_connected():
            return
        self._fetch_and_render_remote(path)

    def _fetch_and_render_remote(self, path: str):
        """获取远程路径内容并渲染"""
        entries = self.file_transfer_service.get_remote_file_list(path)
        self.view.render_remote_children(path, entries)

