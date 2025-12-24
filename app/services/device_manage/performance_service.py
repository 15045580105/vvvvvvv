from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


class PerformanceFetchError(Exception):
    """采集远程性能指标或进程列表失败。"""


@dataclass
class PerformanceMetrics:
    cpu: float
    mem: float
    disk_usage: float
    disk_read_kb: float
    disk_write_kb: float

@dataclass
class ProcessSample:
    type: str
    user: str
    pid: int
    cpu_percent: float
    mem_percent: float
    vsz_kb: int
    rss_kb: int
    tty: str
    stat: str
    start_time: str
    cpu_time: str
    container: str
    process_name: str
    full_command: str
    group_name: Optional[str] = None


class PerformanceService:
    """通过 SSHClient 发指令采集样机的性能/进程数据的服务。"""

    def __init__(
        self,
        device_service,
        executor: Optional[Callable[[str, int], Tuple[int, str, str]]] = None,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        use_dummy: bool = True,
    ) -> None:
        self._device_service = device_service
        self._executor = executor
        self._target: Optional[tuple[str, int]] = None
        self._use_dummy = use_dummy
        # 从 device_service 获取 ssh_client 实例
        self._ssh_client = self._device_service.get_ssh_client()

        # State for calculating rates
        self._prev_cpu = None
        self._prev_disk_io = None
        self._prev_disk_time = None
        self._use_dummy = False

    def fetch_metrics(self, timeout: int = 5) -> PerformanceMetrics:
        """采集 CPU / 内存 / 磁盘指标。"""
        # 每次采集前，重新从 DeviceService 获取最新的 SSHClient 实例（确保状态同步）
        self._ssh_client = self._device_service.get_ssh_client()

        # 1. CPU
        cpu_usage = 0.0
        current_cpu = self.get_cpu_usage()
        if current_cpu and self._prev_cpu:
            total_time_diff = current_cpu['total_time'] - self._prev_cpu['total_time']
            idle_time_diff = current_cpu['idle_time'] - self._prev_cpu['idle_time']

            if total_time_diff > 0:
                cpu_usage = 100.0 * (total_time_diff - idle_time_diff) / total_time_diff

        self._prev_cpu = current_cpu

        # 2. Memory
        mem_usage = 0.0
        memory = self.get_memory_usage()
        if memory:
            mem_usage = memory['usage_percent']

        # 3. Disk I/O
        disk_usage = 0.0
        read_kb = 0.0
        write_kb = 0.0

        disk_io = self.get_disk_io()
        if disk_io:
            disk_usage = disk_io['usage_percent']
            read_kb = disk_io['read_kb']
            write_kb = disk_io['write_kb']

        return PerformanceMetrics(
            cpu=cpu_usage,
            mem=mem_usage,
            disk_usage=disk_usage,
            disk_read_kb=read_kb,
            disk_write_kb=write_kb
        )


    def fetch_processes(self, limit: int = 20, timeout: int = 8) -> List[ProcessSample]:
        """采集进程列表。"""
        # 每次采集前，重新从 DeviceService 获取最新的 SSHClient 实例
        self._ssh_client = self._device_service.get_ssh_client()

        if self._ssh_client is None or not self._ssh_client.is_connected():
            # raise PerformanceFetchError("SSH设备未连接，无法采集进程数据")
            return []

        command = "ps aux"
        stdout = self._ssh_client.execute_command(command)
        if not stdout:
            return []

        return self._parse_process_output(stdout)

    @staticmethod
    def _parse_process_output(stdout: str) -> List[ProcessSample]:
        lines = stdout.strip().split('\n')
        processes = []

        # Skip header if present
        if len(lines) > 0 and "PID" in lines[0]:
            lines = lines[1:]

        for line in lines:
            if not line.strip():
                continue

            # 匹配格式: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
            pattern = r'^(\S+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+([\d:]+)\s+(.+)$'
            match = re.match(pattern, line)

            if not match:
                parts = line.split()
                if len(parts) < 11:
                    continue
                try:
                    user, pid, cpu, mem, vsz, rss, tty, stat, start, time = parts[:10]
                    command = ' '.join(parts[10:])
                except (IndexError, ValueError):
                    continue
            else:
                user, pid, cpu, mem, vsz, rss, tty, stat, start, time, command = match.groups()

            # Initialize
            p_type = 'unknown'
            container = 'unknown'
            process_name = 'unknown'

            # Logic from processmonitor.py
            if command.startswith('/containers/'):
                p_type = 'type1'
                path_parts = command.split()[0].split('/')
                if len(path_parts) > 3:
                    container = path_parts[2]
                    process_name = path_parts[-1]
            elif command.strip() == '/bin/sh /containers/NeuSARPlatform/neusar_startup.sh':
                p_type = 'type2'
                container = 'NeuSARPlatform'
                process_name = 'neusar_startup.sh'

            try:
                processes.append(ProcessSample(
                    type=p_type,
                    user=user,
                    pid=int(pid),
                    cpu_percent=float(cpu),
                    mem_percent=float(mem),
                    vsz_kb=int(vsz),
                    rss_kb=int(rss),
                    tty=tty,
                    stat=stat,
                    start_time=start,
                    cpu_time=time,
                    container=container,
                    process_name=process_name,
                    full_command=command
                ))
            except ValueError:
                continue

        return processes


    def get_cpu_usage(self):
        """获取CPU使用率"""
        # 从/proc/stat读取CPU信息
        command = "cat /proc/stat | grep '^cpu '"
        output = self._ssh_client.execute_command(command)

        if not output:
            return None

        # 解析CPU数据: user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
        cpu_data = re.findall(r'\d+', output)
        if len(cpu_data) < 4:
            return None

        # 计算总CPU时间和空闲时间
        total_time = sum(map(int, cpu_data))
        idle_time = int(cpu_data[3])  # idle是第4个字段

        return {
            'total_time': total_time,
            'idle_time': idle_time,
            'usage_percent': None  # 需要两次测量才能计算百分比
        }

    def get_memory_usage(self):
        """获取内存使用情况"""
        command = "free -k | grep Mem:"
        output = self._ssh_client.execute_command(command)

        if not output:
            return None

        # 解析内存数据: total, used, free, shared, buff/cache, available
        mem_data = re.findall(r'\d+', output)
        if len(mem_data) < 6:
            return None

        total = int(mem_data[0])
        used = int(mem_data[1])
        free = int(mem_data[2])
        available = int(mem_data[5])

        usage_percent = (used / total) * 100 if total > 0 else 0

        return {
            'total_kb': total,
            'used_kb': used,
            'free_kb': free,
            'available_kb': available,
            'usage_percent': usage_percent
        }

    def get_disk_io(self):
        """获取磁盘I/O统计和使用率"""
        # 修改命令，匹配更广泛的磁盘设备，包括mmcblk设备
        command = "cat /proc/diskstats | grep -E '^(\\s*[0-9]+\\s+[0-9]+\\s+)(mmcblk0|sd|vd|hd)[a-z]* ' | head -1"
        output = self._ssh_client.execute_command(command)

        if not output:
            # 如果上面的命令没有返回结果，尝试获取第一个非零设备
            command = "cat /proc/diskstats | head -1"
            output = self._ssh_client.execute_command(command)

        if not output:
            return None

        # 解析磁盘I/O数据
        # 使用更灵活的正则表达式匹配数字，适应不同格式的空格
        io_data = re.findall(r'\d+', output)
        if len(io_data) < 11:
            return None

        # 读取和写入的扇区数（1扇区=512字节）
        # 根据/proc/diskstats格式，第6个字段是读取的扇区数，第10个字段是写入的扇区数
        read_sectors = int(io_data[5])
        write_sectors = int(io_data[9])

        # 获取I/O操作时间（毫秒），第13个字段
        io_time_ms = int(io_data[12]) if len(io_data) > 12 else 0
        # 获取加权I/O操作时间（毫秒），第14个字段
        weighted_io_time_ms = int(io_data[13]) if len(io_data) > 13 else 0

        current_time = time.time()
        usage_percent = 0.0

        # 计算磁盘使用率（基于I/O操作时间）
        if self._prev_disk_io and self._prev_disk_time:
            time_diff = current_time - self._prev_disk_time
            if time_diff > 0:
                # 计算I/O操作时间的增量
                io_time_diff = io_time_ms - self._prev_disk_io['io_time_ms']
                # 转换为使用率百分比（I/O时间占总时间的比例）
                usage_percent = min(100.0, (io_time_diff / (time_diff * 1000)) * 100)

        # 保存当前状态用于下一次计算
        self._prev_disk_io = {
            'read_sectors': read_sectors,
            'write_sectors': write_sectors,
            'io_time_ms': io_time_ms,
            'weighted_io_time_ms': weighted_io_time_ms
        }
        self._prev_disk_time = current_time

        return {
            'read_sectors': read_sectors,
            'write_sectors': write_sectors,
            'read_kb': read_sectors * 0.5,  # 转换为KB
            'write_kb': write_sectors * 0.5,  # 转换为KB
            'io_time_ms': io_time_ms,
            'weighted_io_time_ms': weighted_io_time_ms,
            'usage_percent': usage_percent
        }

    def get_system_info(self):
        """获取系统基本信息"""
        # 获取主机名
        hostname_cmd = "hostname"
        hostname = self._ssh_client.execute_command(hostname_cmd) or "Unknown"

        # 获取系统负载
        loadavg_cmd = "cat /proc/loadavg"
        loadavg = self._ssh_client.execute_command(loadavg_cmd) or "0 0 0"
        load_1, load_5, load_15 = loadavg.split()[:3]

        # 获取系统运行时间
        uptime_cmd = "cat /proc/uptime"
        uptime_output = self._ssh_client.execute_command(uptime_cmd) or "0"
        uptime_seconds = float(uptime_output.split()[0])

        return {
            'hostname': hostname,
            'load_1min': float(load_1),
            'load_5min': float(load_5),
            'load_15min': float(load_15),
            'uptime_seconds': uptime_seconds
        }
