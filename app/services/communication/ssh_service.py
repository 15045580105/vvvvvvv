from typing import Dict, Tuple, Optional

from app.services.communication.ssh_pool import SSHConnectionPool

HostKey = Tuple[str, int]


class SSHService:
    """对外暴露的 SSH 服务：

    - 动态注册主机 (host, port, 认证信息)
    - 复用底层 SSHConnectionPool 长连接
    - 提供单条和批量命令执行接口
    """

    def __init__(self, pool: Optional[SSHConnectionPool] = None) -> None:
        self._pool = pool or SSHConnectionPool()
        # key: (host, port) -> {username, password, key_file}
        self._hosts: Dict[HostKey, dict] = {}

    def register_host(
        self,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        eager_connect: bool = False,
    ) -> None:
        """注册一台 SSH 主机。

        eager_connect=True 时会立即建立一次连接，后续复用。
        """
        key = (host, port)
        self._hosts[key] = {
            "username": username,
            "password": password,
            "key_file": key_file,
        }

        if eager_connect:
            # 轻量探活命令
            self.execute(host, port, "echo SSH OK")

    def execute(
        self,
        host: str,
        port: int,
        command: str,
        timeout: int = 30,
    ) -> Tuple[str, str, int]:
        """对指定 (host, port) 执行命令。"""
        key = (host, port)
        cfg = self._hosts.get(key)
        if not cfg:
            raise ValueError(f"SSHService: 主机尚未注册: {host}:{port}")

        return self._pool.exec(
            host=host,
            port=port,
            username=cfg["username"],
            password=cfg.get("password"),
            key_file=cfg.get("key_file"),
            command=command,
            timeout=timeout,
        )

    def execute_many(
        self,
        commands: Dict[HostKey, str],
        timeout: int = 30,
    ) -> Dict[HostKey, dict]:
        """对多台主机执行各自的命令。

        commands: { (host, port): command }
        返回: { (host, port): {success, output, error, exit_code} }
        """
        results: Dict[HostKey, dict] = {}
        for (host, port), cmd in commands.items():
            try:
                out, err, code = self.execute(host, port, cmd, timeout=timeout)
                results[(host, port)] = {
                    "success": True,
                    "output": out,
                    "error": err,
                    "exit_code": code,
                }
            except Exception as e:
                results[(host, port)] = {
                    "success": False,
                    "output": "",
                    "error": str(e),
                    "exit_code": -1,
                }
        return results

    def close_host(self, host: str, port: int) -> None:
        self._pool.close_one(host, port)

    def close_all(self) -> None:
        self._pool.close_all()

