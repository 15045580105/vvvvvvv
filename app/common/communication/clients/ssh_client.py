import logging
import os
import paramiko
import socket
import threading
import traceback
from typing import Optional, Dict, Any


logger = logging.getLogger(__name__)

class SSHClient:
    """
    SSH客户端封装类 (单例模式)
    系统任何时候都只会有一条SSH连接
    """
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(SSHClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._lock = threading.RLock()
        self._client: Optional[paramiko.SSHClient] = None
        self._connected = False
        self._hostname = None
        self._port = 22
        self._username = None
        self._password = None
        self.last_connect_error: Optional[str] = None
        self.last_connect_exception: Optional[Exception] = None
        self._initialized = True

    def _build_disconnect_log(self, *, source: str, reason: str, include_stack: bool = False) -> str:
        with self._lock:
            client = self._client
            hostname = self._hostname
            port = self._port
            connected = self._connected

        transport_alive = False
        try:
            transport = client.get_transport() if client else None
            transport_alive = bool(transport and transport.is_active())
        except Exception:
            transport_alive = False

        message = (
            f"[SSH断开] source={source or 'unknown'} | reason={reason or '--'} | "
            f"thread={threading.current_thread().name} | target={hostname or '--'}:{port or 22} | "
            f"connected={connected} | transport_alive={transport_alive}"
        )

        if include_stack:
            stack = traceback.extract_stack(limit=8)[:-2]
            formatted = " <- ".join(
                f"{frame.name}@{os.path.basename(frame.filename)}:{frame.lineno}"
                for frame in stack[-4:]
            )
            if formatted:
                message += f" | stack={formatted}"

        return message

    def _build_connection_state_text(self) -> str:
        with self._lock:
            client = self._client
            hostname = self._hostname
            port = self._port
            connected = self._connected

        transport_alive = False
        try:
            transport = client.get_transport() if client else None
            transport_alive = bool(transport and transport.is_active())
        except Exception:
            transport_alive = False

        return (
            f"thread={threading.current_thread().name} | target={hostname or '--'}:{port or 22} | "
            f"connected={connected} | transport_alive={transport_alive}"
        )

    def _log_passive_disconnect(self, stage: str, detail: str = "") -> None:
        message = f"[SSH被动掉线] stage={stage} | {self._build_connection_state_text()}"
        if detail:
            message += f" | detail={detail}"
        logger.warning(message)

    def connect(
        self,
        hostname: str,
        port: int = 22,
        username: str = None,
        password: str = None,
        timeout: float = 20,
        *,
        auth_timeout: float | None = None,
        banner_timeout: float | None = None,
        look_for_keys: bool = False,
        allow_agent: bool = False,
        **extra_connect_args,
    ) -> bool:
        """
        建立SSH连接。如果当前已有连接，会先断开旧连接，确保系统只有一条连接。
        """
        old_client = None
        with self._lock:
            # 如果已有连接，先断开
            old_client = self._client
            self._client = None
            self._connected = False

            self._hostname = hostname
            self._port = port
            self._username = username
            self._password = password

        if old_client:
            try:
                old_client.close()
            except Exception:
                pass

        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_args = {
                "hostname": hostname,
                "port": port,
                "timeout": timeout,
                "look_for_keys": look_for_keys,
                "allow_agent": allow_agent,
            }
            if username:
                connect_args["username"] = username
            if password:
                connect_args["password"] = password
            if auth_timeout is not None:
                connect_args["auth_timeout"] = auth_timeout
            if banner_timeout is not None:
                connect_args["banner_timeout"] = banner_timeout
            if extra_connect_args:
                connect_args.update(extra_connect_args)

            client.connect(**connect_args)
            with self._lock:
                self._client = client
                self._connected = True
            return True

        except paramiko.AuthenticationException as e:
            self.last_connect_error = f"认证失败(用户名/密码错误): {e}"
            self.last_connect_exception = e
            logger.warning(f"SSH连接失败: {self.last_connect_error}")
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            with self._lock:
                self._client = None
                self._connected = False
            return False

        except paramiko.SSHException as e:
            self.last_connect_error = f"SSH协议错误: {e}"
            self.last_connect_exception = e
            logger.warning(f"SSH连接失败: {self.last_connect_error}")
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            with self._lock:
                self._client = None
                self._connected = False
            return False

        except socket.timeout as e:
            self.last_connect_error = f"连接超时: {e}"
            self.last_connect_exception = e
            logger.warning(f"SSH连接失败: {self.last_connect_error}")
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            with self._lock:
                self._client = None
                self._connected = False
            return False

        except ConnectionRefusedError as e:
            self.last_connect_error = f"连接被拒绝(目标主机拒绝连接): {e}"
            self.last_connect_exception = e
            logger.warning(f"SSH连接失败: {self.last_connect_error}")
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            with self._lock:
                self._client = None
                self._connected = False
            return False

        except Exception as e:
            self.last_connect_error = f"{type(e).__name__}: {e}"
            self.last_connect_exception = e
            logger.warning(f"SSH连接失败: {self.last_connect_error}")
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            with self._lock:
                self._client = None
                self._connected = False
            return False

    def disconnect(self, *, source: str = "unknown", reason: str = "", include_stack: bool = False):
        """断开SSH连接。

        source/reason 用于标记“是谁触发了真正断开”，便于排查共享 SSH 被谁关闭。
        """
        logger.warning(self._build_disconnect_log(source=source, reason=reason, include_stack=include_stack))
        client = None
        with self._lock:
            client = self._client
            self._client = None
            self._connected = False
        if client:
            try:
                client.close()
            except Exception:
                pass

    def is_connected(self) -> bool:
        """获取当前的连接状态"""
        with self._lock:
            client = self._client
            connected = self._connected
        if not client or not connected:
            return False
        # 可选：发送心跳包检测连接是否真的存活
        try:
            transport = client.get_transport()
            alive = bool(transport and transport.is_active())
        except Exception:
            alive = False
        if not alive:
            with self._lock:
                if self._client is client:
                    self._connected = False
            self._log_passive_disconnect("is_connected", "transport not active")
        return alive

    def execute_command(self, command: str) -> Optional[str]:
        """
        在远程主机上执行命令

        Args:
            command: 要执行的命令

        Returns:
            命令输出结果 (stdout)，如果出错返回 None
        """
        result = self.execute_command_detailed(command)
        if not result.get("ok"):
            return None
        return result.get("stdout")

    def execute_command_detailed(self, command: str) -> Dict[str, Any]:
        """执行远程命令并返回详细结果，便于业务层输出精确日志。"""
        if not self.is_connected():
            self._log_passive_disconnect("execute_command_precheck", f"command={command}")
            if self._hostname:
                if not self.connect(self._hostname, self._port, self._username, self._password):
                    return {
                        "ok": False,
                        "stdout": "",
                        "stderr": "SSH 未连接，且自动重连失败",
                        "exit_status": None,
                        "exception": None,
                    }
            else:
                return {
                    "ok": False,
                    "stdout": "",
                    "stderr": "SSH 未连接，且无可用历史连接信息",
                    "exit_status": None,
                    "exception": None,
                }

        with self._lock:
            client = self._client

        if client is None:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "SSH client 不存在",
                "exit_status": None,
                "exception": None,
            }

        try:
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            exit_status = None
            try:
                exit_status = stdout.channel.recv_exit_status()
            except Exception:
                pass

            ok = not error and (exit_status in (None, 0))
            return {
                "ok": ok,
                "stdout": output,
                "stderr": error,
                "exit_status": exit_status,
                "exception": None,
            }

        except Exception as e:
            passive_detail = f"command={command}; exception={str(e)}"
            try:
                transport = client.get_transport()
                if not (transport and transport.is_active()):
                    with self._lock:
                        if self._client is client:
                            self._connected = False
                    self._log_passive_disconnect("execute_command_exception", passive_detail)
            except Exception:
                with self._lock:
                    if self._client is client:
                        self._connected = False
                self._log_passive_disconnect("execute_command_exception_transport_check_failed", passive_detail)
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "exit_status": None,
                "exception": str(e),
            }

    def get_client(self) -> Optional[paramiko.SSHClient]:
        """获取底层的paramiko Client对象"""
        with self._lock:
            return self._client
