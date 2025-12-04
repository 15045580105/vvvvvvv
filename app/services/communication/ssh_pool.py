import threading
from typing import Dict, Tuple, Optional

import paramiko


class SSHConnectionPool:
    """SSH 连接池：按 (host, port) 维度复用长连接。

    - 为每个 (host, port) 维护一个 paramiko.SSHClient
    - 自动检测连接是否仍然可用，失效时重连
    - 提供统一的命令执行接口 exec()
    - 提供 close_one/close_all 进行资源清理
    """

    def __init__(self) -> None:
        # key: (host, port) -> paramiko.SSHClient
        self._conns: Dict[Tuple[str, int], paramiko.SSHClient] = {}
        self._lock = threading.Lock()

    def _get_or_create(
        self,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        timeout: int = 10,
    ) -> paramiko.SSHClient:
        """获取一个可用连接，没有就创建并缓存。

        该方法是线程安全的，适合多线程并发访问同一连接池实例。
        """
        key = (host, port)
        with self._lock:
            client = self._conns.get(key)

            # 如果已经有连接，检查是否仍然活着
            if client is not None:
                transport = client.get_transport()
                if transport is not None and transport.is_active():
                    return client
                # 已失效，尝试关闭并移除
                try:
                    client.close()
                except Exception:
                    pass
                self._conns.pop(key, None)

            # 创建新连接
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_file:
                # 使用私钥认证
                pkey = paramiko.RSAKey.from_private_key_file(key_file)
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    pkey=pkey,
                    timeout=timeout,
                )
            else:
                # 使用用户名密码认证
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=timeout,
                )

            self._conns[key] = client
            return client

    @staticmethod
    def _decode(data: bytes) -> str:
        """对远程输出做容错解码，支持常见编码，避免乱码抛异常。"""
        if not data:
            return ""
        for enc in ("utf-8", "gbk", "gb2312", "latin1"):
            try:
                return data.decode(enc, errors="strict").strip()
            except UnicodeDecodeError:
                continue
        # 所有尝试失败时，退回到忽略错误的 utf-8
        return data.decode("utf-8", errors="ignore").strip()

    def exec(
        self,
        host: str,
        port: int,
        username: str,
        command: str,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, str, int]:
        """在指定主机上执行命令，返回 (stdout, stderr, exit_code)。

        注意：不会自动关闭连接，连接会被缓存以便后续复用，
        上层应通过 close_one/close_all 在适当时机统一回收。
        """
        client = self._get_or_create(host, port, username, password, key_file)

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        # 等待命令完成并获取退出码
        exit_code = stdout.channel.recv_exit_status()

        out = self._decode(stdout.read())
        err = self._decode(stderr.read())
        return out, err, exit_code

    def close_one(self, host: str, port: int) -> None:
        """关闭某个 (host, port) 的 SSH 连接。"""
        key = (host, port)
        with self._lock:
            client = self._conns.pop(key, None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def close_all(self) -> None:
        """关闭池中所有连接。"""
        with self._lock:
            items = list(self._conns.items())
            self._conns.clear()
        for (_host, _port), client in items:
            try:
                client.close()
            except Exception:
                pass

    def __del__(self) -> None:
        # 作为兜底保证，防止忘记显式关闭
        try:
            self.close_all()
        except Exception:
            pass

