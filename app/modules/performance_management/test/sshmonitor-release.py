#!/usr/bin/env python3
"""
远程Linux系统监控程序
通过SSH连接远程Linux系统，监控CPU、内存和IO使用率
监控周期：1秒一次
"""

import paramiko
import time
import re
from datetime import datetime


class RemoteSystemMonitor:
    def __init__(self, hostname, port=22, username=None, password=None):
        """
        初始化SSH连接参数

        Args:
            hostname: 远程主机IP地址
            port: SSH端口，默认22
            username: 用户名
            password: 密码
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.ssh_client = None
        self.connected = False

        # 用于存储前一次的磁盘IO统计，用于计算使用率
        self.prev_disk_io = None
        self.prev_disk_time = None

    def connect(self):
        """建立SSH连接"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 如果未提供用户名和密码，尝试使用密钥认证
            if self.username and self.password:
                self.ssh_client.connect(
                    self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=10
                )
            else:
                # 使用系统默认的SSH密钥
                self.ssh_client.connect(
                    self.hostname,
                    port=self.port,
                    timeout=10
                )

            self.connected = True
            print(f"成功连接到 {self.hostname}:{self.port}")
            return True

        except Exception as e:
            print(f"SSH连接失败: {e}")
            return False

    def disconnect(self):
        """断开SSH连接"""
        if self.ssh_client:
            self.ssh_client.close()
            self.connected = False
            print("SSH连接已断开")

        # 重置磁盘IO统计
        self.prev_disk_io = None
        self.prev_disk_time = None

    def execute_command(self, command):
        """
        在远程主机上执行命令

        Args:
            command: 要执行的命令

        Returns:
            命令输出结果
        """
        if not self.connected:
            if not self.connect():
                return None

        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()

            if error:
                print(f"命令执行错误: {error}")
                return None

            return output
        except Exception as e:
            print(f"命令执行异常: {e}")
            return None

    def get_cpu_usage(self):
        """获取CPU使用率"""
        # 从/proc/stat读取CPU信息
        command = "cat /proc/stat | grep '^cpu '"
        output = self.execute_command(command)

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
        output = self.execute_command(command)

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
        output = self.execute_command(command)

        if not output:
            # 如果上面的命令没有返回结果，尝试获取第一个非零设备
            command = "cat /proc/diskstats | head -1"
            output = self.execute_command(command)

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
        if self.prev_disk_io and self.prev_disk_time:
            time_diff = current_time - self.prev_disk_time
            if time_diff > 0:
                # 计算I/O操作时间的增量
                io_time_diff = io_time_ms - self.prev_disk_io['io_time_ms']
                # 转换为使用率百分比（I/O时间占总时间的比例）
                usage_percent = min(100.0, (io_time_diff / (time_diff * 1000)) * 100)

        # 保存当前状态用于下一次计算
        self.prev_disk_io = {
            'read_sectors': read_sectors,
            'write_sectors': write_sectors,
            'io_time_ms': io_time_ms,
            'weighted_io_time_ms': weighted_io_time_ms
        }
        self.prev_disk_time = current_time

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
        hostname = self.execute_command(hostname_cmd) or "Unknown"

        # 获取系统负载
        loadavg_cmd = "cat /proc/loadavg"
        loadavg = self.execute_command(loadavg_cmd) or "0 0 0"
        load_1, load_5, load_15 = loadavg.split()[:3]

        # 获取系统运行时间
        uptime_cmd = "cat /proc/uptime"
        uptime_output = self.execute_command(uptime_cmd) or "0"
        uptime_seconds = float(uptime_output.split()[0])

        return {
            'hostname': hostname,
            'load_1min': float(load_1),
            'load_5min': float(load_5),
            'load_15min': float(load_15),
            'uptime_seconds': uptime_seconds
        }

    def format_bytes(self, bytes_value):
        """格式化字节大小为易读格式"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

    def format_uptime(self, seconds):
        """格式化运行时间"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{days}d {hours}h {minutes}m"

    def monitor_system(self, interval=1, duration=60):
        """
        监控系统资源使用情况

        Args:
            interval: 监控间隔（秒）
            duration: 总监控时长（秒）
        """
        if not self.connect():
            print("无法建立SSH连接，监控终止")
            return

        print(f"开始监控系统 {self.hostname}:{self.port}")
        print(f"监控间隔: {interval}秒, 总时长: {duration}秒")
        print("=" * 80)

        # 用于计算CPU使用率的初始值
        prev_cpu = None
        start_time = time.time()
        count = 0

        # 获取系统基本信息
        system_info = self.get_system_info()
        print(f"主机名: {system_info['hostname']}")
        print(f"系统负载: {system_info['load_1min']:.2f} ({system_info['load_5min']:.2f}, {system_info['load_15min']:.2f})")
        print(f"运行时间: {self.format_uptime(system_info['uptime_seconds'])}")
        print("=" * 80)

        try:
            while time.time() - start_time < duration:
                count += 1
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                print(f"\n第 {count} 次监控 - {current_time}")
                print("-" * 50)

                # 获取内存使用情况
                memory = self.get_memory_usage()
                if memory:
                    print(f"内存使用率: {memory['usage_percent']:.1f}%")
                    print(
                        f"内存使用: {self.format_bytes(memory['used_kb'] * 1024)} / {self.format_bytes(memory['total_kb'] * 1024)}")
                    print(f"可用内存: {self.format_bytes(memory['available_kb'] * 1024)}")

                # 获取磁盘I/O
                disk_io = self.get_disk_io()
                if disk_io:
                    print(f"磁盘读取: {disk_io['read_kb']:.1f} KB")
                    print(f"磁盘写入: {disk_io['write_kb']:.1f} KB")
                    print(f"磁盘使用率: {disk_io['usage_percent']:.1f}%")

                # 获取CPU使用率（需要两次测量）
                current_cpu = self.get_cpu_usage()
                if current_cpu and prev_cpu:
                    total_time_diff = current_cpu['total_time'] - prev_cpu['total_time']
                    idle_time_diff = current_cpu['idle_time'] - prev_cpu['idle_time']

                    if total_time_diff > 0:
                        cpu_usage = 100.0 * (total_time_diff - idle_time_diff) / total_time_diff
                        print(f"CPU使用率: {cpu_usage:.1f}%")

                prev_cpu = current_cpu

                # 等待下一次监控
                elapsed = time.time() - start_time
                remaining = duration - elapsed

                if remaining > interval:
                    time.sleep(interval)
                elif remaining > 0:
                    time.sleep(remaining)
                else:
                    break

        except KeyboardInterrupt:
            print("\n监控被用户中断")
        except Exception as e:
            print(f"监控过程中发生错误: {e}")
        finally:
            self.disconnect()
            print(f"\n监控结束，总共进行了 {count} 次监控")


def main():
    """主函数"""
    # 远程主机配置
    HOSTNAME = "10.1.0.79"  # 下位机IP
    PORT = 22  # SSH端口

    # 如果远程主机需要用户名和密码认证，请在这里设置
    USERNAME = "root"  # 设置为你的用户名，如 "root"
    PASSWORD = "$ww0328_G"  # 设置为你的密码

    # 监控参数
    MONITOR_INTERVAL = 1  # 监控间隔：1秒
    MONITOR_DURATION = 60  # 监控时长：60秒

    print("远程Linux系统监控程序")
    print("=" * 50)

    # 创建监控器实例
    monitor = RemoteSystemMonitor(
        hostname=HOSTNAME,
        port=PORT,
        username=USERNAME,
        password=PASSWORD
    )

    # 开始监控
    monitor.monitor_system(
        interval=MONITOR_INTERVAL,
        duration=MONITOR_DURATION
    )


if __name__ == "__main__":
    main()
