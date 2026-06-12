import datetime
import os
import sys
import threading

from PyQt5 import QtWidgets, QtCore

from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.core.event_bus import event_bus
from app.modules.file_transfer.model.file_transfer_model import FileTransferModel
from app.modules.file_transfer.view.file_transfer_view import FileTransferView
from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService


class FileTransferController(BaseController):
    # Defining signals for thread-safe UI updates
    refresh_local_signal = QtCore.pyqtSignal()
    refresh_remote_signal = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        self.model = FileTransferModel()
        self.view = FileTransferView()
        super().__init__(self.model, self.view, parent)

        self.config_service = ConfigService()
        self.device_service = di_container.resolve(DeviceService)
        if not self.device_service:
            self.device_service = DeviceService()
            di_container.register_singleton(DeviceService, self.device_service)

        self.model.bind_device_service(self.device_service)
        self.device_service.protocol_status_changed_signal.connect(self._on_protocol_status_changed)

        # Internal signals connection
        self.refresh_local_signal.connect(self.refresh_local_directory)
        self.refresh_remote_signal.connect(self._refresh_remote_current_path)

        self._init_view_connections()
        self._init_device_list()
        self.load_local_roots()

        # Listen to device list changes
        try:
            event_bus.device_list_changed.connect(self._init_device_list)
        except Exception as e:
            print(f"Warning: could not connect to event_bus: {e}")

    def _init_view_connections(self):
        # Local signals
        self.view.refresh_local_requested.connect(self.refresh_local_directory)
        self.view.local_path_entered.connect(self.change_local_directory)
        self.view.local_item_expanded.connect(self.handle_local_item_expanded)
        self.view.local_item_clicked.connect(self.on_local_item_clicked)
        self.view.go_up_local_requested.connect(self.go_up_local)
        self.view.browse_local_requested.connect(self.browse_local_directory)

        # Remote signals
        self.view.refresh_remote_requested.connect(self.refresh_remote_directory)
        self.view.remote_path_entered.connect(self.change_remote_directory)
        self.view.remote_item_expanded.connect(self.handle_remote_item_expanded)
        self.view.remote_item_clicked.connect(self.on_remote_item_clicked)
        self.view.go_up_remote_requested.connect(self.go_up_remote)

        # Transfer signals
        self.view.upload_requested.connect(self.handle_upload_request)
        self.view.download_requested.connect(self.handle_download_request)

    def _init_device_list(self):
        """Load devices from ConfigService into ComboBox"""
        current_data = self.view.get_selected_device()
        self.view.device_combo.clear()

        devices = self.config_service.load_devices()
        for dev in devices:
            name = dev.get('name', 'Unknown')
            ip = dev.get('ip', '')
            display = f"{name} ({ip})"
            self.view.device_combo.addItem(display, dev)

        # Restore selection if possible (by IP)
        if current_data:
             for i in range(self.view.device_combo.count()):
                 d = self.view.device_combo.itemData(i)
                 if d and d.get('ip') == current_data.get('ip'):
                     self.view.device_combo.setCurrentIndex(i)
                     break

    # ---------------- Local File System Logic ----------------
    def load_local_roots(self):
        roots = []
        if sys.platform.startswith('win'):
            import string
            from ctypes import windll
            drives = []
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(f"{letter}:\\")
                bitmask >>= 1
            roots = drives
        else:
            roots = ['/']
        self.view.set_local_roots(roots)

    def refresh_local_directory(self):
        path = self.view.local_path_edit.text()
        if path and os.path.exists(path):
            self.change_local_directory(path)
            self.view._expand_tree_to_path(self.view.local_tree, path)
        else:
            self.load_local_roots()

    def browse_local_directory(self):
        default_dir = self.view.local_path_edit.text() or "C:/"
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self.view, "选择本地目录", default_dir)
        if dir_path:
            self.change_local_directory(dir_path)

    def go_up_local(self):
        current_path = self.view.local_path_edit.text()
        if not current_path: return

        if sys.platform.startswith('win') and len(current_path) <= 3 and current_path.endswith(':\\'):
             return

        parent_path = os.path.dirname(current_path)
        if parent_path and os.path.exists(parent_path):
            self.change_local_directory(parent_path)

    def change_local_directory(self, path):
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return

        self.view.local_path_edit.setText(path)
        # 获取该目录下的所有文件和文件夹
        items = self.get_local_directory_content(path)
        found = self.view.update_node_children(path, items, is_remote=False)
        if not found:
            # 路径不在当前树中，重置树根为该路径
            self.view.set_local_root(path)
            self.view.update_node_children(path, items, is_remote=False)
        self.view._expand_tree_to_path(self.view.local_tree, path)

    def handle_local_item_expanded(self, path):
        self.change_local_directory(path)

    def on_local_item_clicked(self, path):
        # Already handled in View signal emission, but we might want to refresh?
        pass

    def get_local_directory_content(self, path):
        items = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    name = entry.name
                    try:
                        stat_info = entry.stat()
                        mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M')
                        size = self._format_size(stat_info.st_size) if entry.is_file() else ""
                        item_type = "文件夹" if entry.is_dir() else "文件"
                        items.append((name, mtime, item_type, size))
                    except OSError:
                        continue
        except Exception as e:
            print(f"Read error {path}: {e}")

        items.sort(key=lambda x: (x[2] != "文件夹", x[0].lower()))
        return items

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    # ---------------- Remote File System Logic ----------------
    def refresh_remote_directory(self):
        ssh_client = self.device_service.get_ssh_client() if self.device_service else None
        if ssh_client is None or not ssh_client.is_connected():
            self.view.show_toast("未连接设备")
            return

        # Ensure model uses the global connection
        if not self.model.use_global_connection():
             self.view.show_toast("无法获取SSH会话")
             return

        path = self.view.remote_path_edit.text()
        if not path:
             path = "/log"

        self.change_remote_directory(path)
        self.view._expand_tree_to_path(self.view.remote_tree, path)

    def _on_protocol_status_changed(self, payload: dict):
        """连接状态变化后，及时让文件传输模块丢弃旧的 SCP/SFTP 包装对象。"""
        ssh_status = str(payload.get("ssh_connect_status", ""))
        if ("连接失败" in ssh_status) or ("已断开" in ssh_status) or ("未连接" in ssh_status):
            self.model.disconnect()
            return

        if "建链成功" in ssh_status:
            # 只重绑传输层包装对象，不关闭共享 SSH 主连接。
            self.model.use_global_connection()

    def change_remote_directory(self, path):
        if not self.model.connected: return

        path = path.replace('\\', '/')
        if not path.startswith('/'): path = '/' + path
        path = path.rstrip('/') or '/'

        self.view.remote_path_edit.setText(path)
        items = self.model.list_remote_dir(path)

        if items is not None:
             found = self.view.update_node_children(path, items, is_remote=True)
             if not found:
                 # 路径不在当前树中，重置树根为该路径
                 self.view.set_remote_root(path)
                 self.view.update_node_children(path, items, is_remote=True)
             self.view._expand_tree_to_path(self.view.remote_tree, path)

    def handle_remote_item_expanded(self, path):
         self.change_remote_directory(path)

    def on_remote_item_clicked(self, path):
        pass

    def go_up_remote(self):
        current_path = self.view.remote_path_edit.text()
        if not current_path or current_path == '/': return

        parent_path = os.path.dirname(current_path.rstrip('/')) or '/'
        parent_path = parent_path.replace('\\', '/')
        self.change_remote_directory(parent_path)

    # ---------------- Transfer Logic ----------------
    def handle_upload_request(self):
        # Use view.local_tree.selectedItems() logic
        selected_items = self.view.local_tree.selectedItems()
        if not selected_items:
            self.view.show_info("提示", "请选择要上传的文件")
            return

        remote_path = self.view.remote_path_edit.text()
        if not remote_path:
            self.view.show_info("提示", "请指定远程目录")
            return

        local_paths = [item.data(0, QtCore.Qt.UserRole) for item in selected_items if item.data(0, QtCore.Qt.UserRole)]

        # Start Thread
        t = threading.Thread(target=self._upload_task, args=(local_paths, remote_path))
        t.daemon = True
        t.start()

    def _upload_task(self, local_paths, remote_dir):
        if not self.model.scp_client: return

        self.view.append_log(f"开始上传 {len(local_paths)} 个项目到 {remote_dir}")
        for path in local_paths:
            try:
                self.model.scp_client.put(path, remote_dir, recursive=True)
                self.view.append_log(f"上传成功: {os.path.basename(path)}")
            except Exception as e:
                self.view.append_log(f"上传失败 {os.path.basename(path)}: {e}")

        self.refresh_remote_signal.emit()

    def handle_download_request(self):
        selected_items = self.view.remote_tree.selectedItems()
        if not selected_items:
            self.view.show_info("提示", "请选择要下载的文件")
            return

        local_dir = self.view.local_path_edit.text()
        if not local_dir:
            self.view.show_info("提示", "请指定本地目录")
            return

        remote_paths = [item.data(0, QtCore.Qt.UserRole) for item in selected_items if item.data(0, QtCore.Qt.UserRole)]

        t = threading.Thread(target=self._download_task, args=(remote_paths, local_dir))
        t.daemon = True
        t.start()

    def _download_task(self, remote_paths, local_dir):
        if not self.model.scp_client: return

        self.view.append_log(f"开始下载 {len(remote_paths)} 个项目到 {local_dir}")
        for path in remote_paths:
            try:
                self.model.scp_client.get(path, local_dir, recursive=True)
                self.view.append_log(f"下载成功: {os.path.basename(path)}")
            except Exception as e:
                self.view.append_log(f"下载失败 {os.path.basename(path)}: {e}")

        self.refresh_local_signal.emit()

    def _refresh_remote_current_path(self):
        """Helper to refresh remote view without full reconnect logic if possible"""
        path = self.view.remote_path_edit.text()
        if not path: path = "/log"
        self.change_remote_directory(path)
