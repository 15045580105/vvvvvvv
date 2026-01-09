import datetime
import stat
import paramiko
from PyQt5.QtCore import pyqtSignal
from app.core.base_service import BaseService


class FileTransferService(BaseService):
    connection_status_changed = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.ssh_client = None
        self._connected = False

    def connect_device(self, hostname, port=22, username=None, password=None):
        """建立SSH连接"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if username and password:
                self.ssh_client.connect(
                    hostname,
                    port=port,
                    username=username,
                    password=password,
                    timeout=10
                )
            else:
                self.ssh_client.connect(
                    hostname,
                    port=port,
                    timeout=10
                )
            self._connected = True
            self.connection_status_changed.emit(True, "Connected")
            return True
        except Exception as e:
            print(f"SSH连接失败: {e}")
            self._connected = False
            self.connection_status_changed.emit(False, str(e))
            return False

    def disconnect(self):
        """断开SSH连接"""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        self._connected = False
        self.connection_status_changed.emit(False, "Disconnected")

    def is_connected(self):
        return self._connected and self.ssh_client is not None

    def get_remote_file_list(self, path: str):
        """获取远程目录内容，返回 View 所需的结构列表"""
        if not self.ssh_client:
            return []

        # 优先尝试 SFTP
        try:
            sftp = self.ssh_client.open_sftp()
            return self._get_entries_sftp(sftp, path)
        except Exception as e:
            # Fallback to SSH exec
            print(f"SFTP failed, fallback to SSH: {e}")
            return self._get_entries_ssh(path)

    def _get_entries_sftp(self, sftp, path):
        children = []
        try:
            for attr in sftp.listdir_attr(path):
                name = attr.filename
                if name in ('.', '..'): continue

                is_dir = stat.S_ISDIR(attr.st_mode)
                full_path = (path.rstrip('/') + '/' + name).replace('//', '/')

                size_str = self._format_size(attr.st_size) if not is_dir else ""
                try:
                    mtime_str = datetime.datetime.fromtimestamp(attr.st_mtime).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    mtime_str = ""

                children.append({
                    "name": name,
                    "path": full_path,
                    "is_dir": is_dir,
                    "size_kb": size_str,  # Using size_kb as generic size label
                    "mtime": mtime_str
                })
        except Exception as e:
            print(f"SFTP list error: {e}")

        # Sort: Dirs first, then files
        children.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return children

    def _get_entries_ssh(self, path):
        # TODO: Implement SSH ls fallback
        return []

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

