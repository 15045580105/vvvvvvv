from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from app.services.communication.ssh_service import SSHService


class PerformanceFetchError(Exception):
    """采集远程性能指标或进程列表失败。"""


@dataclass
class PerformanceMetrics:
    cpu: float
    mem: float
    mem_bw: float


@dataclass
class ProcessSample:
    user: str
    pid: int
    cpu_percent: float
    mem_percent: float
    virt: int
    res: int
    command: str
    group_name: Optional[str] = None


class PerformanceService:
    """通过 SSH 采集远程 PC 性能/进程数据的服务。"""

    def __init__(
        self,
        ssh_service: Optional[SSHService] = None,
        executor: Optional[Callable[[str, int], Tuple[int, str, str]]] = None,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        use_dummy: bool = True,
    ) -> None:
        self._ssh_service = ssh_service or SSHService()
        self._executor = executor
        self._target: Optional[tuple[str, int]] = None
        self._use_dummy = use_dummy

        if host and port and username:
            self.configure_target(host, port, username, password=password, key_file=key_file)
            # 用户显式配置了 SSH 目标后默认关闭 dummy
            self._use_dummy = use_dummy

    def configure_target(
        self,
        host: str,
        port: int,
        username: str,
        *,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        eager_connect: bool = False,
    ) -> None:
        """配置 SSH 目标主机，可反复调用以切换目标。"""
        self._target = (host, port)
        self._ssh_service.register_host(
            host=host,
            port=port,
            username=username,
            password=password,
            key_file=key_file,
            eager_connect=eager_connect,
        )

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def fetch_metrics(self, timeout: int = 5) -> PerformanceMetrics:
        """采集 CPU / 内存 / 内存带宽指标。"""
        command = "get_perf_metrics"
        return self._parse_metrics_output(*self._execute(command, timeout))

    def fetch_processes(self, limit: int = 20, timeout: int = 8) -> List[ProcessSample]:
        """采集进程列表，默认返回前 limit 条。"""
        command = f"get_process_list --limit {limit}"
        return self._parse_process_output(*self._execute(command, timeout))

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _execute(self, command: str, timeout: int) -> Tuple[int, str, str]:
        if self._executor:
            return self._executor(command, timeout)

        if self._target:
            host, port = self._target
            stdout, stderr, exit_code = self._ssh_service.execute(host, port, command, timeout=timeout)
            return exit_code, stdout, stderr

        if self._use_dummy:
            return self._dummy_executor(command)

        raise PerformanceFetchError("PerformanceService: 未配置 SSH 目标，也未启用 dummy 模式。")

    @staticmethod
    def _parse_metrics_output(returncode: int, stdout: str, stderr: str) -> PerformanceMetrics:
        if returncode != 0:
            raise PerformanceFetchError(f"性能命令执行失败: {stderr.strip() or returncode}")

        line = (stdout or "").strip()
        if not line:
            raise PerformanceFetchError("未获取到性能指标数据")

        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            raise PerformanceFetchError(f"性能指标格式不正确: {line}")

        try:
            cpu, mem, mem_bw = (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError as exc:  # pragma: no cover - 数据异常直接抛出
            raise PerformanceFetchError(f"无法解析性能指标: {line}") from exc

        for name, value in (("CPU", cpu), ("内存", mem), ("内存带宽", mem_bw)):
            if not 0.0 <= value <= 100.0:
                raise PerformanceFetchError(f"{name} 数值超出范围: {value}")

        return PerformanceMetrics(cpu=cpu, mem=mem, mem_bw=mem_bw)

    @staticmethod
    def _parse_process_output(returncode: int, stdout: str, stderr: str) -> List[ProcessSample]:
        if returncode != 0:
            raise PerformanceFetchError(f"进程采集失败: {stderr.strip() or returncode}")

        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        if not lines:
            return []

        processes: List[ProcessSample] = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                # 跳过无法解析的行，但保留其它数据
                continue
            try:
                user = parts[0]
                pid = int(parts[1])
                cpu_percent = float(parts[2])
                mem_percent = float(parts[3])
                virt = int(parts[4])
                res = int(parts[5])
                command = parts[6]
                group_name = parts[7] if len(parts) > 7 and parts[7] else None
            except ValueError:
                continue

            processes.append(
                ProcessSample(
                    user=user,
                    pid=pid,
                    cpu_percent=cpu_percent,
                    mem_percent=mem_percent,
                    virt=virt,
                    res=res,
                    command=command,
                    group_name=group_name,
                )
            )

        return processes

    @staticmethod
    def _dummy_executor(command: str, timeout: int = 5) -> Tuple[int, str, str]:  # pragma: no cover - UI 调试占位
        if "get_process_list" in command:
            limit = 20
            if "--limit" in command:
                try:
                    limit = int(command.split("--limit")[-1].strip().split()[0])
                except ValueError:
                    limit = 20
            lines = []
            users = ["root", "system", "user1", "user2"]
            groups = ["Core", "Service", "User", "Others"]
            commands = [
                "diagnostic_service",
                "memory_manager",
                "logger_daemon",
                "python app.py",
                "java -jar service.jar",
            ]
            for idx in range(limit):
                user = random.choice(users)
                pid = 1200 + idx
                cpu = random.uniform(0, 40)
                mem = random.uniform(0, 30)
                virt = random.randint(50_000, 500_000)
                res = random.randint(10_000, 200_000)
                cmd = random.choice(commands)
                group = random.choice(groups)
                lines.append(f"{user},{pid},{cpu:.1f},{mem:.1f},{virt},{res},{cmd},{group}")
            return 0, "\n".join(lines), ""

        cpu = random.uniform(10, 80)
        mem = random.uniform(20, 90)
        mem_bw = random.uniform(5, 95)
        return 0, f"{cpu:.1f},{mem:.1f},{mem_bw:.1f}", ""
