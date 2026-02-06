from app.core.base_model import BaseModel
import paramiko
import scp
import os
import stat
from datetime import datetime
from app.common.communication.clients.ssh_client import SSHClient


class FileTransferModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.local_path = "C:/Diagnostics/Logs"
        self.remote_filter = ""
        self.tasks = []

        self.ssh_client = None
        self.scp_client = None
        self.sftp_client = None
        self.connected = False
        self.current_device_info = None  # Store (ip, port, user)


    def use_global_connection(self):
        """Use the global SSH client connection"""
        global_client = SSHClient()
        if not global_client.is_connected():
            return False

        self.ssh_client = global_client.get_client()
        if self.ssh_client and self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
            # Init SCP
            self.scp_client = scp.SCPClient(self.ssh_client.get_transport())

            # Init SFTP if possible
            try:
                self.sftp_client = self.ssh_client.open_sftp()
            except Exception as e:
                print(f"SFTP not available: {e}")
                self.sftp_client = None

            self.connected = True
            return True
        return False

    def connect(self, ip, port, user, password):
        """Connect to remote device via SSH"""
        # If already connected to the same device, do nothing
        if self.connected and self.current_device_info == (ip, port, user):
            if self.ssh_client and self.ssh_client.get_transport().is_active():
                return True

        self.disconnect()

        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(ip, port=port, username=user, password=password, timeout=10)

            # Init SCP
            # progress callback can be passed here if needed, but we handle it in controller or wrap it
            self.scp_client = scp.SCPClient(self.ssh_client.get_transport())

            # Init SFTP
            try:
                self.sftp_client = self.ssh_client.open_sftp()
            except Exception as e:
                print(f"SFTP not available: {e}")
                self.sftp_client = None

            self.connected = True
            self.current_device_info = (ip, port, user)
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        if self.scp_client:
            try:
                self.scp_client.close()
            except:
                pass
            self.scp_client = None

        if self.sftp_client:
            try:
                self.sftp_client.close()
            except:
                pass
            self.sftp_client = None

        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None

        self.connected = False
        self.current_device_info = None

    def list_remote_dir(self, path):
        """List remote directory content. Returns list of tuples: (name, mtime, type, size)"""
        if not self.connected:
            return None

        if self.sftp_client:
            return self._list_sftp(path)
        else:
            return self._list_ssh(path)

    def _list_sftp(self, path):
        items = []
        try:
            for entry in self.sftp_client.listdir_attr(path):
                name = entry.filename
                # Skip . and ..
                if name in ('.', '..'):
                    continue
                timestamp = entry.st_mtime
                mtime = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
                is_dir = stat.S_ISDIR(entry.st_mode)
                ftype = "文件夹" if is_dir else "文件"
                size = self._format_size(entry.st_size) if not is_dir else ""

                items.append((name, mtime, ftype, size))

            # Sort: Folder first, then Name
            items.sort(key=lambda x: (x[2] != "文件夹", x[0].lower()))
            return items
        except Exception as e:
            print(f"SFTP List error: {e}")
            return None

    def _list_ssh(self, path):
        """SSH 执行 ls -l 命令列出目录内容"""
        items = []

        # 1. 优先方案：尝试使用 --time-style 格式化时间，便于解析
        cmd = f"ls -l --time-style=+%Y-%m-%d__%H:%M '{path}'"
        stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
        lines = stdout.readlines()

        use_fallback = False
        # 如果没有输出（通常意味着命令不支持该参数，如 Busybox），则启用备用方案
        if not lines:
             use_fallback = True

        # 2. 兜底方案：通用 ls -l
        if use_fallback:
             cmd = f"ls -l '{path}'"
             stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
             lines = stdout.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith('total'):
                continue

            parts = line.split()
            if len(parts) < 6:
                continue

            # 3. 解析基础信息
            perms = parts[0]
            is_dir = perms.startswith('d')
            ftype = "文件夹" if is_dir else "文件"

            # 4. 动态解析列（大小、时间、文件名）
            # 分支 A: 使用了 --time-style (标准格式: 权限 链接 用户 组 大小 日期__时间 文件名)
            if not use_fallback and len(parts) >= 7:
                 try:
                     size_bytes = int(parts[4])
                     dt_str = parts[5].replace('__', ' ')
                     name = ' '.join(parts[6:])
                 except:
                     name = parts[-1]
                     size_bytes = 0
                     dt_str = ""

            # 分支 B: 兜底通用格式 (日期通常占3列: Month Day Time/Year)
            else:
                 # 假设结构: 权限 链接 用户 组 大小 M D Y Name
                 if len(parts) >= 9:
                      try:
                          size_bytes = int(parts[4])
                          name = ' '.join(parts[8:])
                          dt_str = ' '.join(parts[5:8])
                      except:
                           name = parts[-1]
                           size_bytes = 0
                           dt_str = ""
                 else:
                      name = parts[-1]
                      size_bytes = 0
                      dt_str = ""

            if name in ('.', '..'): continue

            size = self._format_size(size_bytes) if not is_dir else ""
            items.append((name, dt_str, ftype, size))

        # 5. 排序：文件夹优先，再按名称
        items.sort(key=lambda x: (x[2] != "文件夹", x[0].lower()))
        return items

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def remote_path_exists(self, path):
        if not self.connected:
            return False

        if self.sftp_client:
            try:
                self.sftp_client.stat(path)
                return True
            except FileNotFoundError:
                return False
        else:
            # Use test -e
            stdin, stdout, stderr = self.ssh_client.exec_command(f"test -e '{path}'")
            return stdout.channel.recv_exit_status() == 0

    def is_remote_file(self, path):
        if not self.connected:
            return False

        if self.sftp_client:
            try:
                s = self.sftp_client.stat(path)
                return not stat.S_ISDIR(s.st_mode)
            except:
                return False
        else:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"test -f '{path}'")
            return stdout.channel.recv_exit_status() == 0
