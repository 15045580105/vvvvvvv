import os
from datetime import datetime

from app.core.base_controller import BaseController
from app.modules.file_transfer.model.file_transfer_model import FileTransferModel
from app.modules.file_transfer.view.file_transfer_view import FileTransferView


class FileTransferController(BaseController):
    def __init__(self, parent=None):
        self.model = FileTransferModel(parent)
        self.view = FileTransferView(parent)
        super().__init__(self.model, self.view, parent)

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
        # 初始化远程树（此处使用示例数据，真实环境下应从服务层获取）
        self._init_remote_tree()

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
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return ""

    # --- 远程文件树相关业务逻辑 ---
    def _init_remote_tree(self):
        """初始化远程树根节点。

        真实项目中，这里应从远程设备查询根路径（如 /log）下的目录/文件。
        这里先用示例路径展示层级结构设计。
        """
        root_path = "/log"
        root_name = "log"
        self.view.render_remote_tree(root_name, root_path)
        # 加载第一层子级（示例）
        self._populate_remote_children(root_path, self._get_mock_remote_files())

    def on_remote_refresh_clicked(self):
        """远程刷新按钮点击。"""
        root_path = "/log"
        self.view.render_remote_tree("log", root_path)
        self._populate_remote_children(root_path, self._get_mock_remote_files())

    def on_remote_filter_changed(self, text: str):
        """远程搜索框内容改变。这里只做简单本地过滤示例。"""
        # 简单处理：按关键字过滤 mock 数据后重建树
        all_files = self._get_mock_remote_files()
        if text:
            filtered = [f for f in all_files if
                        text.lower() in f["path"].lower() or text.lower() in (f.get("appid") or "").lower()]
        else:
            filtered = all_files
        root_path = "/log"
        self.view.render_remote_tree("log", root_path)
        self._populate_remote_children(root_path, filtered)

    def on_remote_dir_expanded(self, path: str):
        """远程目录节点展开时，填充其子节点。"""
        # 在实际实现中，这里根据 path 去远程设备请求该目录的子项。
        # 目前用 mock 数据按前缀匹配模拟。
        all_files = self._get_mock_remote_files()
        related = [f for f in all_files if f["path"].startswith(path.rstrip("/ ") + "/")]
        self._populate_remote_children(path, related)

    def _populate_remote_children(self, parent_path: str, files: list):
        """将一批远程文件记录按路径拆分为目录树，传给 View 渲染。

        files: List[{
            'path': str, 'appid': str, 'size_kb': str, 'ctime': str, 'mtime': str
        }]
        """
        # 构造当前 parent_path 直接子级的目录和文件
        parent_norm = parent_path.rstrip("/") or "/"
        child_dirs = set()
        leaf_files = []

        for f in files:
            full_path = f["path"].lstrip("/")
            parent_norm_no_slash = parent_norm.lstrip("/")
            if parent_norm_no_slash and not full_path.startswith(parent_norm_no_slash + "/"):
                continue
            # 去掉 parent 前缀
            rel = full_path[len(parent_norm_no_slash):].lstrip("/") if parent_norm_no_slash else full_path
            if not rel:
                continue
            parts = rel.split("/", 1)
            first = parts[0]
            if len(parts) == 1:
                # 直接位于 parent_path 下的文件
                leaf_files.append(f)
            else:
                # 子目录
                child_dirs.add(first)

        children = []
        # 目录节点
        for d in sorted(child_dirs):
            child_path = (parent_norm.rstrip("/") + "/" + d).replace("//", "/")
            children.append({
                "name": d,
                "path": child_path,
                "is_dir": True,
                "appid": "",
                "size_kb": "",
                "ctime": "",
                "mtime": "",
            })
        # 文件节点
        for f in sorted(leaf_files, key=lambda x: x["path"].lower()):
            children.append({
                "name": os.path.basename(f["path"]),
                "path": f["path"],
                "is_dir": False,
                "appid": f.get("appid", ""),
                "size_kb": f.get("size_kb", ""),
                "ctime": f.get("ctime", ""),
                "mtime": f.get("mtime", ""),
            })

        self.view.render_remote_children(parent_path, children)

    # --- 模拟远程文件数据，展示树状设计 ---
    def _get_mock_remote_files(self) -> list:
        """示例远程文件数据。

        真正实现时，请替换为从远程设备查询返回的文件列表。
        """
        return [
            {"path": "/log/app1/2025/11/log_2025_11_01.txt", "appid": "app1", "size_kb": "12",
             "ctime": "2025-11-01 10:00", "mtime": "2025-11-01 10:05"},
            {"path": "/log/app1/2025/11/log_2025_11_02.txt", "appid": "app1", "size_kb": "20",
             "ctime": "2025-11-02 09:00", "mtime": "2025-11-02 09:10"},
            {"path": "/log/app1/2025/12/log_2025_12_01.txt", "appid": "app1", "size_kb": "25",
             "ctime": "2025-12-01 08:00", "mtime": "2025-12-01 08:10"},
            {"path": "/log/app2/trace/trace_001.pcap", "appid": "app2", "size_kb": "1024", "ctime": "2025-11-20 14:00",
             "mtime": "2025-11-20 14:30"},
            {"path": "/log/app2/trace/trace_002.pcap", "appid": "app2", "size_kb": "2048", "ctime": "2025-11-21 15:00",
             "mtime": "2025-11-21 15:45"},
            {"path": "/log/system/syslog.txt", "appid": "sys", "size_kb": "5", "ctime": "2025-11-10 12:00",
             "mtime": "2025-11-10 12:01"},
        ]
