import paramiko
import re
from typing import List, Dict, Any
import time


class ProcessMonitor:
    def __init__(self, hostname: str, username: str, password: str, port: int = 22):
        """
        初始化SSH连接参数

        Args:
            hostname: 远程主机IP地址
            username: SSH用户名
            password: SSH密码
            port: SSH端口，默认22
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.ssh_client = None

    def connect(self) -> bool:
        """建立SSH连接"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10
            )
            print(f"成功连接到 {self.hostname}")
            return True
        except Exception as e:
            print(f"SSH连接失败: {e}")
            return False

    def execute_command(self, command: str) -> str:
        """执行远程命令并返回结果[3,5](@ref)"""
        if not self.ssh_client:
            if not self.connect():
                return ""

        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()

            if error:
                print(f"命令执行错误: {error}")
                return ""

            return output
        except Exception as e:
            print(f"命令执行异常: {e}")
            return ""

    def parse_process_line(self, line: str) -> Dict[str, Any]:
        """
        解析单行ps aux输出，提取所需信息[4](@ref)

        Args:
            line: ps aux命令的一行输出

        Returns:
            包含解析后进程信息的字典
        """
        if not line.strip():
            return None

        # 使用正则表达式解析ps aux输出格式[6](@ref)
        # 匹配格式: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        pattern = r'^(\S+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+([\d:]+)\s+(.+)$'
        match = re.match(pattern, line)

        if not match:
            # 如果正则匹配失败，使用空格分割（简化处理）
            parts = line.split()
            if len(parts) < 11:
                return None
            try:
                user, pid, cpu, mem, vsz, rss, tty, stat, start, time = parts[:10]
                command = ' '.join(parts[10:])
            except (IndexError, ValueError):
                return None
        else:
            user, pid, cpu, mem, vsz, rss, tty, stat, start, time, command = match.groups()

        # 初始化返回值
        process_info = {
            'user': user,
            'pid': int(pid),
            'cpu_percent': float(cpu),
            'mem_percent': float(mem),
            'vsz_kb': int(vsz),
            'rss_kb': int(rss),
            'tty': tty,
            'stat': stat,
            'start_time': start,
            'cpu_time': time,
            'full_command': command,
            'container': 'unknown',
            'process_name': 'unknown',
            'type': 'unknown'
        }

        # 第一类处理：路径第一个部分为containers
        if command.startswith('/containers/'):
            process_info['type'] = 'type1'
            # 解析路径：/containers/BB/CC/DD/EE/FF/bin/GG
            path_parts = command.split()[0].split('/')  # 取第一个单词（命令路径）并按/分割
            if len(path_parts) > 3:  # 确保有足够的路径组件
                process_info['container'] = path_parts[2]  # BB字段（container）
                process_info['process_name'] = path_parts[-1]  # GG字段（process_name）

        # 第二类处理：特定命令格式
        elif command.strip() == '/bin/sh /containers/NeuSARPlatform/neusar_startup.sh':
            process_info['type'] = 'type2'
            process_info['container'] = 'NeuSARPlatform'
            process_info['process_name'] = 'neusar_startup.sh'

        return process_info

    def get_processes(self) -> List[Dict[str, Any]]:
        """获取并解析所有进程信息[1](@ref)"""
        # 执行ps aux命令[4](@ref)
        ps_command = "ps aux"
        output = self.execute_command(ps_command)

        if not output:
            print("无法获取进程信息")
            return []

        processes = []
        lines = output.strip().split('\n')

        # 跳过标题行
        for line in lines[1:]:
            process_info = self.parse_process_line(line)
            if process_info and process_info['type'] != 'unknown':
                processes.append(process_info)

        return processes

    def display_processes(self, processes: List[Dict[str, Any]]):
        """格式化显示进程信息"""
        if not processes:
            print("未找到符合条件的进程")
            return

        # 打印标题
        header = f"{'TYPE':<6} {'USER':<10} {'PID':<8} {'CPU%':<6} {'MEM%':<6} {'VSZ':<10} {'RSS':<10} {'TTY':<8} {'STAT':<5} {'START':<8} {'TIME':<10} {'CONTAINER':<15} {'PROCESS_NAME':<20}"
        print(header)
        print("=" * 140)

        # 打印每个进程信息
        for process in processes:
            print(f"{process['type']:<6} {process['user']:<10} {process['pid']:<8} "
                  f"{process['cpu_percent']:<6.1f} {process['mem_percent']:<6.1f} "
                  f"{process['vsz_kb']:<10} {process['rss_kb']:<10} {process['tty']:<8} "
                  f"{process['stat']:<5} {process['start_time']:<8} {process['cpu_time']:<10} "
                  f"{process['container']:<15} {process['process_name']:<20}")

    def close(self):
        """关闭SSH连接[5](@ref)"""
        if self.ssh_client:
            self.ssh_client.close()
            print("SSH连接已关闭")


def main():
    """主函数示例"""
    # 配置SSH连接参数
    HOSTNAME = "10.1.0.79"  # 替换为实际IP
    USERNAME = "root"  # 替换为实际用户名
    PASSWORD = "$ww0328_G"  # 替换为实际密码
    PORT = 22  # SSH端口

    # 创建监控器实例
    monitor = ProcessMonitor(
        hostname=HOSTNAME,
        username=USERNAME,
        password=PASSWORD,
        port=PORT
    )

    try:
        for i in range(5):
            print(f"\n{'='*20} 第 {i+1}/5 次采集 {'='*20}")
            # 获取进程信息
            processes = monitor.get_processes()

            # 显示结果
            print("找到的进程信息：")
            monitor.display_processes(processes)

            # 分类统计
            type1_count = sum(1 for p in processes if p['type'] == 'type1')
            type2_count = sum(1 for p in processes if p['type'] == 'type2')

            print(f"\n统计信息：")
            print(f"第一类进程（路径以/containers/开头）: {type1_count} 个")
            print(f"第二类进程（特定命令格式）: {type2_count} 个")
            print(f"总计: {len(processes)} 个")

            if i < 4:
                time.sleep(1)

        # 可选：保存到JSON文件
        # if processes:
        #     import json
        #     with open('processes_info.json', 'w', encoding='utf-8') as f:
        #         # 转换无法序列化的类型
        #         serializable_processes = []
        #         for process in processes:
        #             serializable = process.copy()
        #             # 确保所有值都是可序列化的
        #             for key, value in serializable.items():
        #                 if isinstance(value, (int, float, str)):
        #                     continue
        #                 serializable[key] = str(value)
        #             serializable_processes.append(serializable)
        #
        #         json.dump(serializable_processes, f, indent=2, ensure_ascii=False)
        #     print("结果已保存到 processes_info.json")

    except Exception as e:
        print(f"执行过程中发生错误: {e}")
    finally:
        monitor.close()


if __name__ == "__main__":
    main()