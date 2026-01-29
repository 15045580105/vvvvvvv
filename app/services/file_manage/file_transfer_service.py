from datetime import datetime
import os
import scp
from PyQt5.QtCore import pyqtSignal
from app.core.base_service import BaseService
from app.common.communication.clients.ssh_client import SSHClient
from app.services.file_manage.utils.formatting import format_size as _format_size
from app.services.file_manage.progress.progress import make_scp_progress_adapter


class FileTransferService(BaseService):
    connection_status_changed = pyqtSignal(bool, str)

    def __init__(self, transport=None):
        super().__init__()
        self.ssh_client = None  # type: ignore[assignment]
        self.scp_client = None  # 临时持有的 scp.SCPClient（通常不持久化）
        self.transport = transport  # 可注入的 transport 实现（协议/适配器）
        self._connected = False
        # 初始化进度跟踪变量
        self.transfer_start_time = 0
        self.last_log_time = 0
        # 保护性锁/占位（如需扩展为多线程使用可替换为 threading.Lock）
        self._internal_lock = None

    def connect_device(self, hostname, port=22, username=None, password=None):
        """建立SSH连接并初始化SCP客户端"""
        # Delegate to singleton
        return SSHClient().connect(hostname, port, username, password)

    def disconnect(self):
        """断开SSH连接和SCP客户端"""
        SSHClient().disconnect()
        # Safely emit signal if available (helps static analysis and avoids runtime errors
        # in contexts where the signal object may not expose `emit` directly).
        sig = getattr(self, 'connection_status_changed', None)
        if sig is not None and hasattr(sig, 'emit') and callable(getattr(sig, 'emit')):
            try:
                sig.emit(False, "Disconnected")
            except Exception:
                # Swallow any emit-time exceptions to avoid cascading failures
                pass

    def is_connected(self):
        return SSHClient().is_connected()

    def get_remote_file_list(self, path: str):
        """获取远程目录内容，返回 View 所需的结构列表"""
        client = SSHClient().get_client()
        if not client:
            raise RuntimeError("未连接到远程设备")

        # 使用shell命令获取目录列表
        # 若失败会抛出异常，由 Controller 捕获
        return self._get_entries_shell(client, path)

    def _get_entries_shell(self, client, path):
        """使用shell命令获取目录内容（修正解析与隐藏文件判断）"""
        children = []
        try:
            # 强化调试与防御性编程
            cmd = f"ls -la \"{path}\""
            # print(f"Debug: Executing {cmd}")

            exec_result = client.exec_command(cmd)
            if exec_result is None:
                raise RuntimeError("SSH exec_command returned None")

            stdin, stdout, stderr = exec_result

            # 使用 exit_status 判断命令是否成功
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                err_output = stderr.read().decode('utf-8').strip()
                raise RuntimeError(f"ls 命令失败 (Code {exit_status}): {err_output}")

            output = stdout.read().decode('utf-8')
            lines = output.strip().split('\n')
            if not lines:
                return []

            valid_lines = []
            for line in lines:
                l_s = line.strip()
                if not l_s:
                    continue
                if l_s.lower().startswith("total"):
                    continue
                valid_lines.append(l_s)

            for line in valid_lines:
                try:
                    parts = line.split()

                    name = ""
                    if len(parts) >= 9:
                        name = ' '.join(parts[8:])
                    elif len(parts) > 0:
                         name = parts[-1]

                    if not name or name in ('.', '..'):
                        continue

                    # 这里不跳过隐藏文件，如果需要跳过可取消注释
                    # if name.startswith('.'): continue

                    permissions = parts[0] if parts else ""
                    is_dir = permissions.startswith('d')

                    base_path = path.rstrip('/')
                    full_path = f"{base_path}/{name}"

                    mtime_str = ""
                    try:
                        if len(parts) >= 8:
                            mtime_str = f"{parts[5]} {parts[6]} {parts[7]}"
                    except:
                        pass

                    size_str = ""
                    try:
                        if not is_dir and len(parts) > 4:
                            size_str = _format_size(int(parts[4]))
                    except Exception:
                        size_str = ""

                    children.append({
                        "name": name,
                        "path": full_path,
                        "is_dir": is_dir,
                        "size_kb": size_str,
                        "mtime": mtime_str
                    })
                except Exception as line_err:
                    print(f"解析行失败 '{line}': {line_err}")
                    continue

        except Exception as e:
            print(f"Shell ls命令失败: {e}")
            import traceback
            traceback.print_exc()
            raise e

        # Sort: Dirs first, then files
        try:
            children.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        except Exception:
            pass

        return children


    def upload_file(self, local_path, remote_path, callback=None):
        """上传文件 callback(transferred, total)"""
        if not self.ssh_client:
            return False
        try:
            sftp = self.ssh_client.open_sftp()
            sftp.put(local_path, remote_path, callback=callback)
            sftp.close()
            return True
        except Exception as e:
            print(f"Upload failed: {e}")
            return False

    def _download_file_sftp(self, remote_path, local_path, callback=None):
        """SFTP 下载封装（内部使用，保持独立）。

        这个方法为早期实现，提供与 SFTP 对接的简单包装。重命名为
        `_download_file_sftp` 以避免与后面的 `download_file` 冲突并降低静态检查噪音。
        """
        if not self.ssh_client:
            return False
        try:
            sftp = self.ssh_client.open_sftp()
            sftp.get(remote_path, local_path, callback=callback)
            sftp.close()
            return True
        except Exception as e:
            print(f"Download failed: {e}")
            return False

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _get_scp_client(self, progress=None):
        """Helper to create a temporary SCP client from singleton SSHClient"""
        client = SSHClient().get_client()
        if client and client.get_transport() and client.get_transport().is_active():
            return scp.SCPClient(client.get_transport(), progress=progress)
        return None

    def upload(self, local_path, remote_path):
        """上传文件到远程路径"""
        scp_client = self._get_scp_client()
        if not scp_client:
            raise RuntimeError("未连接到远程服务器")
        try:
            scp_client.put(local_path, remote_path=remote_path)
        except Exception as e:
            raise RuntimeError(f"上传失败: {e}")
        finally:
             scp_client.close()

    def download(self, remote_path, local_path):
        """从远程路径下载文件"""
        scp_client = self._get_scp_client()
        if not scp_client:
            raise RuntimeError("未连接到远程服务器")
        try:
            scp_client.get(remote_path, local_path=local_path)
        except Exception as e:
            raise RuntimeError(f"下载失败: {e}")
        finally:
             scp_client.close()

    def path_exists(self, remote_path):
        """检查远程路径是否存在"""
        client = SSHClient().get_client()
        if not client:
            return False

        try:
            stdin, stdout, stderr = client.exec_command(f"test -e \"{remote_path}\"")
            exit_status = stdout.channel.recv_exit_status()
            return exit_status == 0
        except Exception as e:
            print(f"检查路径失败: {e}")
            return False

    def is_remote_dir(self, remote_path):
        """检查远程路径是否为目录"""
        client = SSHClient().get_client()
        if not client:
            return False

        try:
            # 使用 test -d 检查是否为目录
            stdin, stdout, stderr = client.exec_command(f"test -d \"{remote_path}\"")
            exit_status = stdout.channel.recv_exit_status()
            return exit_status == 0
        except Exception as e:
            print(f"检查远程目录失败: {e}")
            return False

    def get_local_file_list(self, path: str):
        """获取本地目录内容，返回 View 所需的结构列表"""
        children = []
        try:
            entries = list(os.scandir(path))
            dirs = sorted([e for e in entries if e.is_dir(follow_symlinks=False)], key=lambda e: e.name.lower())
            files = sorted([e for e in entries if e.is_file(follow_symlinks=False)], key=lambda e: e.name.lower())

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
                    "size": _format_size(st.st_size),
                    "mtime": self._format_mtime(st.st_mtime),
                })
        except OSError:
            pass

        # Sort: Dirs first, then files
        children.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return children

    @staticmethod
    def _format_mtime(timestamp: float) -> str:
        """格式化文件修改时间为本地可读字符串（YYYY-MM-DD HH:MM）。

        使用标准库 `datetime.fromtimestamp`，同时对异常和无效输入进行
        防护，返回空字符串作为兜底。

        扩展：支持以下输入类型：
         - 数字（秒级时间戳或字符串化的数字）
         - ISO 格式时间字符串（例如 2025-12-09T11:22:33 或 2025-12-09 11:22:33）
         - 其他常见可解析格式，尽量使用 datetime.fromisoformat 或 strptime 解析
        """
        if timestamp is None:
            return ""

        # 1) 尝试将常见的数字时间戳转换为 float
        try:
            ts = float(timestamp)
            # 如果是合理的 unix 时间戳范围（2000-2100 年）则认为是秒级时间戳
            if 946684800 <= ts <= 4102444800:
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OverflowError):
            pass

        # 2) 尝试 ISO 格式解析 (支持 'T' 和 空格 分隔符)
        try:
            if isinstance(timestamp, str):
                s = timestamp.strip()
                # 处理形如 '2025-12-09T11:22:33' 或 '2025-12-09 11:22:33'
                try:
                    dt = datetime.fromisoformat(s)
                    return dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    # 再尝试常见格式
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%b %d %H:%M"):
                        try:
                            dt = datetime.strptime(s, fmt)
                            return dt.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            continue
        except Exception:
            pass

        # 3) 无法解析时返回空字符串（保持兼容性）
        return ""

    def upload_with_conflict_resolution(self, local_path: str, remote_dir: str, overwrite_callback, progress_callback=None):
        """带冲突解决的上传方法"""
        filename = os.path.basename(local_path)
        target_remote_path = os.path.join(remote_dir, filename).replace("\\", "/")

        print(f"Debug: [Upload] {local_path} -> {target_remote_path}")

        if self.path_exists(target_remote_path):
            choice = overwrite_callback(filename)
            if choice == "cancel":
                return "cancelled"
            elif choice == "rename":
                target_remote_path = self._generate_new_remote_path(remote_dir, filename)
                print(f"Debug: [Upload] Renamed target to {target_remote_path}")

        # 构造回调闭包：期望上层传入的 progress_callback 能处理 (transferred, total)，
        # 对于 SCP 传入的回调需适配为 (filename, size, sent) -> make_scp_progress_adapter
        progress_cb_wrapper = None
        if progress_callback:
            progress_cb_wrapper = make_scp_progress_adapter(progress_callback)

        scp_client = self._get_scp_client(progress=progress_cb_wrapper)
        if not scp_client:
             return "not_connected"

        try:
            scp_client.put(local_path, remote_path=target_remote_path, recursive=True)
            return "success"
        except Exception as e:
            return str(e)
        finally:
            scp_client.close()

    def download_with_conflict_resolution(self, remote_path: str, local_dir: str, overwrite_callback, progress_callback=None):
        """带冲突解决的下载方法"""
        filename = os.path.basename(remote_path)
        target_local_path = os.path.join(local_dir, filename)

        print(f"Debug: [Download] {remote_path} -> {target_local_path}")

        if os.path.exists(target_local_path):
            choice = overwrite_callback(filename)
            if choice == "cancel":
                return "cancelled"
            elif choice == "rename":
                target_local_path = self._generate_new_local_path(local_dir, filename)
                print(f"Debug: [Download] Renamed target to {target_local_path}")

        progress_cb_wrapper = None
        if progress_callback:
            progress_cb_wrapper = make_scp_progress_adapter(progress_callback)

        scp_client = self._get_scp_client(progress=progress_cb_wrapper)
        if not scp_client:
             return "not_connected"

        try:
            scp_client.get(remote_path, local_path=target_local_path, recursive=True)
            return "success"
        except Exception as e:
            return str(e)
        finally:
            scp_client.close()

    def upload_with_progress(self, local_path, remote_path, progress_callback=None):
        """上传文件并更新进度，返回字符串结果"""
        progress_cb_wrapper = None
        if progress_callback:
            # 期望 progress_callback 接受统一签名 (transferred, total) 或兼容 adapter
            progress_cb_wrapper = make_scp_progress_adapter(progress_callback)

        scp_client = self._get_scp_client(progress=progress_cb_wrapper)
        if not scp_client:
             return "not_connected"
        try:
            scp_client.put(local_path, remote_path=remote_path, recursive=True)
            # scp 库在回调最后不一定传100%，由上层处理或这里强制？但这里只返回 success
            return "success"
        except Exception as e:
            return str(e)
        finally:
             scp_client.close()

    def download_with_progress(self, remote_path, local_path, progress_callback=None):
        """下载文件并更新进度，返回字符串结果"""
        progress_cb_wrapper = None
        if progress_callback:
            progress_cb_wrapper = make_scp_progress_adapter(progress_callback)

        scp_client = self._get_scp_client(progress=progress_cb_wrapper)
        if not scp_client:
             return "not_connected"
        try:
            scp_client.get(remote_path, local_path=local_path, recursive=True)
            return "success"
        except Exception as e:
            return str(e)
        finally:
            scp_client.close()

    def download_file(self, remote_path, local_path, progress_callback=None):
        """下载文件，支持进度回调。优先尝试 SFTP，失败回退到 SCP。"""
        client = SSHClient().get_client()
        if not client:
            return False, "Not connected"
        
        # Ensure local dir exists
        try:
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir)
        except Exception as e:
            return False, f"Local Dir Error: {e}"

        # 1. 尝试 SFTP (Primary)
        sftp = None
        sftp_err = ""
        try:
            sftp = client.open_sftp()
            # SFTP callback: func(transferred, total) matches progress_callback signature
            sftp.get(remote_path, local_path, callback=progress_callback)
            return True, "Success"
        except Exception as e:
            sftp_err = str(e)
            # print(f"SFTP failed: {e}, falling back to SCP")
        finally:
            if sftp:
                try:
                    sftp.close()
                except:
                    pass

        # 2. 回退到 SCP (Fallback)
        try:
            # SCP callback: func(filename, size, sent) -> 使用 make_scp_progress_adapter 适配
            scp_cb = None
            if progress_callback:
                scp_cb = make_scp_progress_adapter(progress_callback)

            # Use internal helper to get scp client from existing transport
            scp_client = self._get_scp_client(progress=scp_cb)
            if not scp_client:
                 return False, f"SFTP Failed ({sftp_err}); SCP Init Failed"

            try:
                scp_client.get(remote_path, local_path=local_path, recursive=True)
                return True, "Success"
            except Exception as e:
                return False, f"SFTP Failed ({sftp_err}); SCP Failed ({str(e)})"
            finally:
                # Close SCP channel (not transport)
                scp_client.close()

        except Exception as e:
             return False, f"Download Error: {str(e)}"

    def _generate_new_remote_path(self, remote_dir: str, filename: str):
        """生成远程重命名路径"""
        base, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{base}({counter}){ext}"
            new_path = os.path.join(remote_dir, new_filename).replace("\\", "/")
            if not self.path_exists(new_path):
                return new_path
            counter += 1

    def _generate_new_local_path(self, local_dir: str, filename: str):
        """生成本地重命名路径"""
        base, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{base}({counter}){ext}"
            new_path = os.path.join(local_dir, new_filename)
            if not os.path.exists(new_path):
                return new_path
            counter += 1
