import paramiko
import threading
from typing import Optional

class SSHClient:
    """
    SSH客户端封装类 (单例模式)
    系统任何时候都只会有一条SSH连接
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(SSHClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._client: Optional[paramiko.SSHClient] = None
        self._connected = False
        self._hostname = None
        self._port = 22
        self._username = None
        self._password = None
        self._initialized = True

    def connect(self, hostname: str, port: int = 22, username: str = None, password: str = None, timeout: int = 20) -> bool:
        """
        建立SSH连接。如果当前已有连接，会先断开旧连接，确保系统只有一条连接。
        """
        with self._lock:
            # 如果已有连接，先断开
            if self._connected:
                self.disconnect()

            self._hostname = hostname
            self._port = port
            self._username = username
            self._password = password

            try:
                self._client = paramiko.SSHClient()
                self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                connect_args = {
                    "hostname": hostname,
                    "port": port,
                    "timeout": timeout
                }
                if username:
                    connect_args["username"] = username
                if password:
                    connect_args["password"] = password

                self._client.connect(**connect_args)
                self._connected = True
                # print(f"成功连接到 {self._hostname}:{self._port}")
                return True

            except Exception as e:
                print(f"SSH连接失败: {e}")
                self._client = None
                self._connected = False
                return False

    def disconnect(self):
        """断开SSH连接"""
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            self._connected = False
            # print("SSH连接已断开")

    def is_connected(self) -> bool:
        """获取当前的连接状态"""
        if not self._client or not self._connected:
            return False
        # 可选：发送心跳包检测连接是否真的存活
        if self._client.get_transport() and self._client.get_transport().is_active():
            return True
        return False

    def execute_command(self, command: str) -> Optional[str]:
        """
        在远程主机上执行命令

        Args:
            command: 要执行的命令

        Returns:
            命令输出结果 (stdout)，如果出错返回 None
        """
        if not self.is_connected():
            # 尝试重连（如果保存了连接信息）
            if self._hostname:
                # print("连接已断开，尝试重连...")
                if not self.connect(self._hostname, self._port, self._username, self._password):
                    return None
            else:
                return None

        try:
            # print(f"---正在执行命令: {command}")
            # exec_command 是非阻塞的
            stdin, stdout, stderr = self._client.exec_command(command)

            # 读取输出
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            # print(f"---接收反馈: {output}")
            if error:
                # print(f"命令执行错误: {error}")
                return None
            # print(f"命令执行成功: {output}")
            return output

        except Exception as e:
            # print(f"命令执行异常: {e}")
            # 发生异常时可能连接已断开
            if not (self._client.get_transport() and self._client.get_transport().is_active()):
                self._connected = False
            return None

    def get_client(self) -> Optional[paramiko.SSHClient]:
        """获取底层的paramiko Client对象"""
        return self._client
