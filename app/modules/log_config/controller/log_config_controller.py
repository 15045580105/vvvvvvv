from typing import List, Dict, Any, Optional
import configparser
import io
import json
import os
from PyQt5.QtCore import pyqtSignal # Add pyqtSignal import
from app.common.communication.clients.ssh_client import SSHClient  # Add SSHClient import

from app.core.base_service import BaseService
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService


class LogConfigService(BaseService):
    log_signal = pyqtSignal(str) # Add log_signal

    def __init__(self):
        super().__init__()
        self._device_service: Optional[DeviceService] = None
        self._topology_service: Optional[TopologyService] = None
        self._map_file_path: Optional[str] = None # Store the map file path

    def inject_device_service(self, device_service: DeviceService):
        self._device_service = device_service
        # 注入 TopologyService，如果未注入则尝试从 DI 容器获取或创建
        self._topology_service = di_container.resolve(TopologyService)
        if not self._topology_service:
            self._topology_service = TopologyService(device_service)
            di_container.register_singleton(TopologyService, self._topology_service)

    def set_map_file_path(self, path: str):
        """Set the path to process_log_config_map.json."""
        self._map_file_path = path

    def set_ecu_log_level(self, ecus: List[str], level: str) -> bool:
        """为指定的 ECU 设置日志等级。"""
        _log = self.log_signal.emit

        if not self._device_service:
            _log("DeviceService 未注入")
            return False

        # 将日志等级字符串映射为整数值
        level_map = {
            "OFF": 0,
            "FATAL": 1,
            "ERROR": 2,
            "WARN": 3,
            "INFO": 4,
            "DEBUG": 5,
            "VERBOSE": 6
        }
        level_val = level_map.get(level, 4)  # 如果未知默认使用 INFO

        # 将 ECU 名称映射到 DID
        ecu_did_map = {
            "CCU0": 0xBE02,
            "CCU1": 0xBE03,
            "CCUA": 0xBE17  # 根据用户请求假设 CCUA 映射到 BE17
        }

        success_all = True

        for ecu in ecus:
            did = ecu_did_map.get(ecu)
            if not did:
                _log(f"未知 ECU: {ecu}")
                continue

            did_bytes = did.to_bytes(2, 'big')

            # 我们需要从设备服务获取 DoIP 客户端
            doip_client = self._device_service.get_doip_client()
            if not doip_client:
                _log("DoIP 客户端未连接")
                return False

            # --- 第一步：读取当前值 ---
            _log(f"读取当前日志配置 (22 {did:X})...")
            read_cmd = bytes([0x22]) + did_bytes
            resp = doip_client.send_doip_message(read_cmd)

            if not resp or resp[0] != 0x62:
                _log(f"读取失败: {resp.hex(' ').upper() if resp else '无响应'}")
                success_all = False
                continue
            _log(f"当前配置: {resp.hex(' ').upper()}")

            # --- 第二步：写入新配置 (2E DID VAL) ---
            # 2E BE 02 06 (示例)
            # 注意：level_val 可能是 int 或 bytes([val])
            # level_map get returns int
            write_cmd = bytes([0x2E]) + did_bytes + bytes([level_val])

            _log(f"设置日志等级为 {level} ({level_val}) (2E {did:X} {level_val:02X})...")

            # 读取是否为工厂模式，工厂模式不需要走2701安全认证
            is_factory_mode = False
            if self._topology_service:
                factory_mode_str = self._topology_service._get_factory_mode()
                if "工厂模式" in factory_mode_str:
                    is_factory_mode = True
                    _log("检测到用户模式，跳过安全访问")
                else:
                    _log("检测到非工厂模式，执行安全访问")

            else:
                _log("TopologyService 未就绪，默认执行安全访问")

            if not is_factory_mode:
                # 非工厂模式：走完整安全访问流程 (10 03 -> 27 01 -> 2E)
                # execute_secure_routine also updated to not take callback
                write_resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_signal=self.log_signal)
            else:
                # 工厂模式：直接发送 10 03 然后 2E 指令
                # 1. 10 03
                session_cmd = bytes.fromhex("10 03")
                _log(f"发送会话控制: {session_cmd.hex(' ').upper()}")
                rx_sess = self._device_service.send_doip_payload(session_cmd)
                if not rx_sess or rx_sess[0] != 0x50:
                    _log(f"会话控制失败: {rx_sess.hex(' ').upper() if rx_sess else '无响应'}")
                    success_all = False
                    continue

                _log(f"发送写指令: {write_cmd.hex(' ').upper()}")
                write_resp = self._device_service.send_doip_payload(write_cmd)

            if not write_resp:
                _log("设置失败")
                success_all = False
                continue

            # 检查 2E 的正响应是否为 6E
            if write_resp[0] != 0x6E:
                _log(f"设置失败，响应: {write_resp.hex(' ').upper()}")
                success_all = False
                continue

            # --- 第三步：回读验证 (22 DID) ---
            _log(f"回读验证配置 (22 {did:X})...")
            verify_resp = doip_client.send_doip_message(read_cmd)
            if not verify_resp or verify_resp[0] != 0x62:
                _log(f"回读失败: {verify_resp.hex(' ').upper() if verify_resp else '无响应'}")
                success_all = False
                continue

            # 验证值 (假设格式为 62 DID VAL)
            # resp: 62 BE 02 06
            if len(verify_resp) >= 4 and verify_resp[3] == level_val:
                _log(f"当前值: {verify_resp.hex(' ').upper()}, 配置成功！")
            else:
                _log(f"验证失败，当前值: {verify_resp.hex(' ').upper()}")
                success_all = False

        return success_all

    def _ensure_ccua_mode_enabled(self) -> bool:
        """确保 CCUA 处于个性化配置模式 (DID 0xBE17 Bit7 = 1)"""
        _log = self.log_signal.emit

        if not self._device_service:
            _log("DeviceService 未注入")
            return False

        client = self._device_service.get_doip_client()
        if not client:
             _log("DoIP Client 未连接")
             return False

        did = 0xBE17
        did_bytes = did.to_bytes(2, 'big')
        # 读取
        _log(f"读取 DID {did:X} ")
        read_resp = client.send_doip_message(bytes([0x22]) + did_bytes)
        _log(f"返回：{read_resp}")
        if not read_resp or read_resp[0] != 0x62 or len(read_resp) < 4:
            _log(f"读取 DID 失败或响应异常")
            return False

        current_val = read_resp[3]
        _log(f"当前 UDS 值: 0x{current_val:02X}")

        if (current_val & 0x80) == 0:
            new_val = current_val | 0x80
            _log(f"准备切换到个性化模式 (Bit7=0 -> 1)，写入新值: 0x{new_val:02X}")
            write_cmd = bytes([0x2E]) + did_bytes + bytes([new_val])
            # execute_secure_routine no callback
            write_resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_signal=self.log_signal)

            if not write_resp or write_resp[0] != 0x6E:
                _log("切换模式失败 (写入 DID 失败)")
                return False
            _log("模式切换成功")
        else:
            _log("当前已是个性化模式 (Bit7=1)，无需修改")

        return True

    def update_ccua_app_config(self, app_id: str, new_level: str) -> bool:
        """
        修改 APP 日志等级 (先确保能修改文件，再切模式)
        1. SSH 修改远程 JSON 配置 (如果失败则不切模式)
        2. UDS 修改 0xBE17 Bit7 = 1
        3. Sync
        """
        _log = self.log_signal.emit

        _log(f"开始修改 CCUA 应用 {app_id} 配置...")

        # --- 状态标记 ---
        ssh_success = False

        # --- 1. SSH 操作 (Json) ---
        _log(f"准备通过 SSH 修改{app_id}]远程配置文件...")
        try:
            ssh = SSHClient()
            if not ssh.is_connected():
                _log(f" SSH 未连接，无法修改{app_id}文件")
                return False

            # 1.1 获取远程路径
            if not self._map_file_path:
                _log(f"未设置{app_id}]本地映射文件路径，请在导入区域选择JSON文件")
                return False

            local_map_path = self._map_file_path
            if not os.path.exists(local_map_path):
                _log(f"{app_id}]找不到本地映射文件: {local_map_path}")
                return False

            remote_path = None
            try:
                with open(local_map_path, 'r', encoding='utf-8') as f:
                    root_data = json.load(f)

                    # 直接提取 process_log_configs
                    mapping = root_data.get("process_log_configs", {})

                    # 尝试去除 app_id 可能的空格
                    clean_app_id = app_id.strip() if app_id else ""

                    entry = mapping.get(clean_app_id)
                    if entry:
                        remote_path = entry.get("path")
                        print(f"{app_id}对应的配置文件的路径:", remote_path)
                    else:
                        print(f"映射表中未找到APP[{app_id}]")

            except Exception as e:
                _log(f"{app_id}]读取本地映射文件异常: {e}")
                return False

            if not remote_path:
                _log(f"{app_id}]映射文件({local_map_path})中未找到 AppID '{app_id}' 对应的路径")
                return False

            _log(f"{app_id}获取到远程配置文件路径: {remote_path}")

            # 1.2 读取远程 JSON 文件
            _log(f"{app_id}正在读取远程文件: {remote_path}")
            content = ssh.execute_command(f"cat {remote_path}")
            if not content:
                _log(f"{app_id}无法读取远程文件或文件为空: {remote_path}")
                return False

            json_data = None
            try:
                json_data = json.loads(content)
            except json.JSONDecodeError:
                _log(f"{app_id}远程文件内容非 JSON 格式: {content[:50]}...")
                return False

            # 1.3 修改配置
            # TODO sed命令存在一个问题：如果JSON文件没有换行符，而是一行显示，无法正确读取到loglevel对应的值，不够健壮；可以创建一个修改后的配置文件，上传上去。
            old_level = json_data.get("logTraceLogLevel", "UNKNOWN")
            if old_level == new_level:
                _log(f"{app_id}日志等级已是 {new_level}，无需更新文件")
                ssh_success = True
            else:
                _log(f"{app_id}正在修改字段 logTraceLogLevel: {old_level} -> {new_level}")

                # 1.4 使用 sed 直接修改文件，避免回写导致文件被清空
                # 构造 sed 命令: s/"logTraceLogLevel": "OLD"/"logTraceLogLevel": "NEW"/
                search_pattern = f'"logTraceLogLevel": "{old_level}"'
                replace_pattern = f'"logTraceLogLevel": "{new_level}"'

                # -i 表示直接修改文件
                sed_cmd = f"sed -i 's/{search_pattern}/{replace_pattern}/' {remote_path}"

                _log(f"{app_id}正在执行修改指令: {sed_cmd}")
                ssh.execute_command(sed_cmd)

                # 1.5 验证修改是否生效
                verify_content = ssh.execute_command(f"cat {remote_path}")
                try:
                    verify_json = json.loads(verify_content)
                    current_level = verify_json.get("logTraceLogLevel", "UNKNOWN")
                    if current_level == new_level:
                        _log(f"{app_id}文件修改校验通过")
                        ssh_success = True
                    else:
                        _log(f"{app_id}文件修改校验失败，当前仍为: {current_level} (可能由于文件格式不标准导致 sed 匹配失败)")
                        ssh_success = False
                except:
                    _log(f"{app_id}文件修改后校验出现异常或 JSON 损坏")
                    ssh_success = False

        except Exception as e:
            _log(f"{app_id}SSH 操作出现异常: {str(e)}")
            import traceback
            _log(traceback.format_exc())
            return False

        if not ssh_success:
            _log(f"{app_id}文件修改失败，中止后续 UDS 操作")
            return False

        # --- 2. UDS 操作 (0xBE17 Bit7) ---
        # 只有在文件操作确认无误后，才去修改 UDS 模式
        if not self._ensure_ccua_mode_enabled():
            _log(f"{app_id}警告：文件已修改但 UDS 模式切换失败，配置可能不生效")
            # 这里可以选择返回 False，或者 True (部分成功)
            # 鉴于文件已改，还是算成功让用户决定是否重试或重启
            return False

        # --- 3. Exec Sync ---
        try:
            ssh = SSHClient()
            if ssh.is_connected():
                ssh.execute_command("sync")
                _log(f"{app_id}执行 Sync 落盘完成")
        except:
            pass
        return True

    def restart_ccu(self, ecu="CCUA"):
        """重启 CCU (UDS 11 03)"""
        _log = self.log_signal.emit

        if not self._device_service:
            _log("DeviceService 未就绪")
            return False

        # 发送软复位指令
        _log(f"[Service] 正在重启 {ecu} (11 03) ...")

        reset_cmd = bytes([0x11, 0x03])

        try:
            # 发送后设备通常会立即断开或不回复正响应，视具体实现而定
            resp = self._device_service.send_doip_payload(reset_cmd)

            # 1. 检查正响应 51 03
            if resp and len(resp) >= 2 and resp[0] == 0x51:
                _log(f"收到重启确认响应: {resp.hex(' ').upper()} (成功)")
                # 重连设备，并传递当前的日志信号，以便重连日志能打印到日志模块窗口
                self._device_service.reconnect_device(log_signal=self.log_signal)
                return True

            # 2. 检查负响应 7F 11 XX
            if resp and resp[0] == 0x7F:
                _log(f"重启请求被拒绝 (NRC): {resp.hex(' ').upper()}")
                return False

            # 3. 无响应但无异常
            _log(f"指令已发送，未收到标准确认，Payload: {resp.hex(' ') if resp else 'Empty'}")
            return True

        except Exception as e:
            err_msg = str(e)
            # 4. 常见的连接断开错误，视为重启成功的标志
            if any(x in err_msg for x in ["Connection reset", "closed", "Broken pipe", "10053", "10054"]):
                _log(f"连接断开，判定重启指令已生效: {err_msg}")
                # 即使是异常导致的连接断开，也尝试重连并传递日志信号
                self._device_service.reconnect_device(log_signal=self.log_signal)
                return True

            _log(f"发送重启指令时出现异常: {e}")
            return False # 其他异常视为失败

    def batch_update_ccua_apps(self, app_list: List[str], new_level: str, new_logTraceLogMode: str = None) -> bool:
        """
        批量修改 CCUA 应用日志等级。
        流程:
        1. 确保 UDS 模式 (BE17 Bit7=1) - 只做一次
        2. SSH 批量修改所有 APP 的 JSON 文件
        3. SSH Sync - 只做一次
        """
        _log = self.log_signal.emit

        if not app_list:
            _log("应用列表为空")
            return True

        if new_logTraceLogMode:
            _log(f"开始批量处理 {len(app_list)} 个应用，目标等级: {new_level}, 目标模式: {new_logTraceLogMode}")
        else:
            _log(f"开始批量处理 {len(app_list)} 个应用，目标等级: {new_level}")

        # --- 1. UDS 前置操作 ---
        if not self._ensure_ccua_mode_enabled():
            _log("无法进入配置模式 (DID 0xBE17 设置失败)，中止操作")
            return False

        # --- 2. SSH 批量文件操作 ---
        success = True
        try:
            ssh = SSHClient()
            if not ssh.is_connected():
                _log("SSH 未连接，尝试建立连接...")
                # 假设 SSHClient 内部管理连接
                pass

            # 2.1 获取映射表
            if not self._map_file_path:
                _log("未设置本地映射文件路径，请在导入区域选择JSON文件")
                return False

            local_map_path = self._map_file_path
            if not os.path.exists(local_map_path):
                _log(f"找不到本地映射文件: {local_map_path}")
                return False

            mapping = {}
            try:
                with open(local_map_path, 'r', encoding='utf-8') as f:
                    root_data = json.load(f)
                    # 严格按照新结构 process_log_configs 读取
                    mapping = root_data.get("process_log_configs", {})
            except Exception as e:
                _log(f"读取映射文件失败: {e}")
                return False


            files_modified_count = 0

            for app_id in app_list:
                # 严格按照新结构读取
                entry = mapping.get(app_id)
                remote_path = None
                if entry and isinstance(entry, dict):
                    remote_path = entry.get("path")

                if not remote_path:
                    _log(f"APP [{app_id}] 未在映射表中找到 Path，跳过")
                    success = False
                    continue

                # 读取远程文件
                content = ssh.execute_command(f"cat {remote_path}")
                if not content or "No such file" in content:
                    _log(f"APP [{app_id}] 远程文件读取失败: {remote_path}")
                    success = False
                    continue

                try:
                    json_data = json.loads(content)

                    modified = False
                    sed_cmds = []

                    # 修改 Log Level
                    old_l = json_data.get("logTraceLogLevel", "UNKNOWN")
                    if old_l != new_level:
                        # 构造 sed 命令
                        search_str = f'"logTraceLogLevel": "{old_l}"'
                        replace_str = f'"logTraceLogLevel": "{new_level}"'
                        sed_cmds.append(f"s/{search_str}/{replace_str}/")
                        modified = True

                    # 修改 Log Mode (如果指定)
                    if new_logTraceLogMode:
                        old_mode = json_data.get("logTraceLogMode", "UNKNOWN")
                        if old_mode != new_logTraceLogMode:
                            search_mode = f'"logTraceLogMode": "{old_mode}"'
                            replace_mode = f'"logTraceLogMode": "{new_logTraceLogMode}"'
                            sed_cmds.append(f"s/{search_mode}/{replace_mode}/")
                            modified = True

                    if not modified:
                        _log(f"APP [{app_id}] 配置无需修改")
                        continue

                    # 执行命令
                    for cmd in sed_cmds:
                        full_sed_cmd = f"sed -i '{cmd}' {remote_path}"
                        ssh.execute_command(full_sed_cmd)

                    # 验证
                    check_content = ssh.execute_command(f"cat {remote_path}")
                    try:
                        check_json = json.loads(check_content)
                        check_success = True

                        if check_json.get("logTraceLogLevel") != new_level:
                            _log(f"APP [{app_id}] LogLevel 修改失败")
                            check_success = False

                        if new_logTraceLogMode and check_json.get("logTraceLogMode") != new_logTraceLogMode:
                             _log(f"APP [{app_id}] LogMode 修改失败")
                             check_success = False

                        if check_success:
                            _log(f"APP [{app_id}] 配置已更新")
                            files_modified_count += 1
                        else:
                            success = False
                    except:
                        _log(f"APP [{app_id}] 修改后文件校验异常")
                        success = False

                except json.JSONDecodeError:
                    _log(f"APP [{app_id}] JSON 解析失败，跳过")
                    success = False
                    continue

            # --- 3. Sync ---
            if files_modified_count > 0:
                _log("执行文件落盘 (sync)...")
                ssh.execute_command("sync")
                _log("批量修改完成")
            else:
                _log("并未修改任何文件 (可能都已是目标等级或出错)")

        except Exception as e:
            _log(f"SSH 操作发生异常: {str(e)}")
            success = False

        return success


    def _map_val_to_level_str(self, val: int) -> str:
        clean_val = val & 0x7F  # 按位与运算，二进制是 0111 1111
        # 0x00: OFF, 0x01: FATAL, 0x02: ERROR, 0x03: WARN, 0x04: INFO, 0x05: DEBUG, 0x06: VERBOSE
        mapping = {
            0: "OFF", 1: "FATAL", 2: "ERROR", 3: "WARN",
            4: "INFO", 5: "DEBUG", 6: "VERBOSE"
        }
        # 返回mapping中clean_val对应的字符串，找不到则返回 UNKNOWN
        return mapping.get(clean_val, "UNKNOWN")

    def _read_uds_did_byte(self, did_int: int) -> Optional[int]:
        '''根据 DID 读取单字节 UDS 值'''
        if not self._device_service:
            return None
        client = self._device_service.get_doip_client()
        if not client:
            return None
        # 构造 UDS 22 读 DID 请求
        did_bytes = did_int.to_bytes(2, 'big')
        req = bytes([0x22]) + did_bytes
        print("发送 UDS 读 DID 请求:", req.hex(' ').upper())
        # 假设 send_doip_message 返回以 SID 开头的 UDS 负载
        # 响应格式: 62 DID_H DID_L VAL ...
        resp = client.send_doip_message(req)
        print("收到 UDS 响应:", resp.hex(' ').upper() if resp else "无响应")

        if resp and len(resp) >= 4 and resp[0] == 0x62:  # 正响应
            return resp[3]  # resp[3]：返回响应的第 4 个字节（即第一个数据字节，索引从 0 开始）
        return None

    def _get_remote_json_level(self, app_id: str, ssh: SSHClient) -> str:
        # 1. 读取本地映射文件
        if not self._map_file_path:
            print(f"[{app_id}] 获取配置失败: 未导入映射文件")
            return "UNKNOWN"

        local_map_path = self._map_file_path
        if not os.path.exists(local_map_path):
            print(f"[{app_id}] 获取配置失败: 映射文件丢失 {local_map_path}")
            return "UNKNOWN"

        remote_path = None

        try:
            with open(local_map_path, 'r', encoding='utf-8') as f:
                root_data = json.load(f)
                # 严格按照新结构 process_log_configs 读取
                mapping = root_data.get("process_log_configs", {})

                clean_app_id = app_id.strip() if app_id else ""
                entry = mapping.get(clean_app_id)

                if entry and isinstance(entry, dict):
                    remote_path = entry.get("path")
                    # print(f"当前APP[{app_id}]对应的配置文件的路径:", remote_path)
                else:
                    # print(f"映射表中未找到APP[{app_id}]")
                    # 不返回错误字符串，而是 logging 并返回 UNKNOWN
                    # print(f"[{app_id}] 未配置路径")
                    return "UNKNOWN"

        except Exception as e:
            print(f"读取本地映射文件出错: {e}")
            return "UNKNOWN"

        if not remote_path:
            return "UNKNOWN"

        # 2. 读取远程 JSON
        try:
            content = ssh.execute_command(f"cat {remote_path}")
            if not content:
                # print(f"远程 JSON 为空或未找到: {remote_path}")
                print(f"[{app_id}] 远程文件缺失: {remote_path}")
                return "UNKNOWN"

            # 3. 解析 JSON
            try:
                data = json.loads(content)
                return data.get("logTraceLogLevel", "UNKNOWN")
            except json.JSONDecodeError:
                # print(f"解析 {app_id} 的远程 JSON 出错")
                print(f"[{app_id}] JSON 格式损坏")
                return "UNKNOWN"
        except Exception as e:
            # print(f"读取 {app_id} 的远程 JSON 出错: {e}")
            print(f"[{app_id}] 读取远程文件异常: {e}")
            return "UNKNOWN"

    def get_apps(self, ecu_filter: str = "", app_filter: str = "", level_filter: str = "") -> List[Dict[str, Any]]:
        """
        获取应用程序及其日志配置列表。
        使用 SSH 从远程目标获取配置。
        根据传入的过滤条件筛选结果。
        """
        result = []
        try:
            ssh = SSHClient()
            if not ssh.is_connected():
                # 无法连接 SSH
                pass

            # --- 第一阶段：来自 SSH 的基础数据 (dlt_logstorage.conf) ---
            config_path = "/containers/NeuSARPlatform/work/base/common/etc/dlt_logstorage.conf"
            content = ssh.execute_command(f"cat {config_path}")
            if not content:
                # 如果我们无法读取配置，就没有必要继续
                return []
            raw_apps = []
            parser = configparser.ConfigParser(strict=False, interpolation=None)
            parser.read_file(io.StringIO(content))
            for section in parser.sections():
                # 只关心 FILTER 开头的节
                if not section.startswith("FILTER"):
                    continue
                try:
                    app_id = parser.get(section, "LogAppName", fallback="Unknown")
                    ecu_id = parser.get(section, "EcuID", fallback="Unknown")
                    file_no = parser.getint(section, "NOFiles", fallback=0)
                    file_size = parser.getint(section, "FileSize", fallback=0)

                    total_mb = (file_no * file_size) / (1024 * 1024)

                    item = {
                        "app_id": app_id,
                        "ecu_id": ecu_id,
                        "log_level": "UNKNOWN", # Placeholder
                        "file_no": str(file_no),
                        "file_size": str(file_size),
                        "total_size": f"{int(total_mb)}"  # 不保留小数且不带单位
                    }
                    raw_apps.append(item)
                except Exception as e:
                    print(f"解析配置节 {section} 出错: {e}")
                    continue

            # --- 第二阶段：UDS 数据 (ECU 状态) ---
            ecu_status_map = {}
            # 定义我们关心的 ECU DID
            ecu_dids = {"CCU0": 0xBE02, "CCU1": 0xBE03, "CCUA": 0xBE17}

            # 检查设备服务是否可用且有客户端
            if self._device_service:
                for ecu_name, did in ecu_dids.items():
                    val = self._read_uds_did_byte(did)
                    if val is not None:
                        # 存储UDS22服务读取到的值
                        ecu_status_map[ecu_name] = val

            # --- 第三阶段：聚合与筛选 ---
            for app in raw_apps:
                # 3a. 按 ECU 和 AppID 预筛选，避免不必要的 JSON 获取
                if ecu_filter and ecu_filter != "" and app.get("ecu_id") != ecu_filter:
                    continue
                if app_filter and app_filter != "" and app.get("app_id") != app_filter:
                    continue

                # 3b. 解析日志等级
                ecu_id = app['ecu_id']
                level = "UNKNOWN"

                if ecu_id in ["CCU0", "CCU1"]:
                    if ecu_id in ecu_status_map:
                        level = self._map_val_to_level_str(ecu_status_map[ecu_id])
                    else:
                        level = "UNKNOWN" # 如果 UDS 失败，我们不知道状态

                elif ecu_id == "CCUA":
                    val = ecu_status_map.get("CCUA")
                    if val is not None:
                        # 检查 Bit 7 以确定模式
                        is_individual_mode = (val & 0x80) != 0 # 检查 Bit 7
                        # 第七位为0表示全局模式，为1表示个性化模式
                        if not is_individual_mode:
                            # 全局模式：使用位 0-6
                            level = self._map_val_to_level_str(val)
                        else:
                            # 个性化模式：读取远程 JSON
                            # 仅在通过预筛选时获取！
                            level = self._get_remote_json_level(app['app_id'], ssh)
                    else:
                        level = "UNKNOWN"

                app['log_level'] = level

                # 3c. 按日志等级筛选
                if level_filter and level_filter != "" and app.get("log_level") != level_filter:
                    continue

                result.append(app)

        except Exception as e:
            print(f"获取日志配置出错: {e}")
            return []

        return result

    def export_logs(self, app_ids: List[str], destination: str) -> bool:
        """Export logs for selected apps."""
        print(f"正在将 {app_ids} 的日志导出到 {destination}")
        return True

    def delete_logs(self, app_ids: List[str]) -> bool:
        """Delete logs for selected apps."""
        print(f"正在删除 {app_ids} 的日志")
        return True

    def restore_config(self, options: Dict[str, bool]) -> Dict[str, Any]:
        """Restore default configuration based on options."""
        # Helper to log
        _log = self.log_signal.emit

        result = {"success": True, "restart_required": False}

        # a) Restore CCUA
        if options.get("restore_ccua"):
            _log("开始恢复 CCUA 默认配置...")
            if not self._restore_ccua_default():
                result["success"] = False
                _log("CCUA 默认配置恢复失败")
            else:
                # ccua_apps = self.get_apps("CCUA", "", "")
                self.batch_update_ccua_apps(["CCUA"], "ERROR", "NETWORK")
                _log("CCUA 默认配置恢复成功")
                result["restart_required"] = True # Need confirm restart in UI

        # b) Restore CCU0
        if options.get("restore_ccu0"):
            _log("开始恢复 CCU0 默认配置...")
            # b) 发送 UDS 2E BE 02 02
            if not self._set_did_byte(0xBE02, 0x02, "CCU0"):
                 result["success"] = False
                 _log("CCU0 默认配置恢复失败")
            else:
                 _log("CCU0 默认配置恢复成功")

        # c) Restore CCU1
        if options.get("restore_ccu1"):
            _log("开始恢复 CCU1 默认配置...")
            # c) 发送 UDS 2E BE 03 02
            if not self._set_did_byte(0xBE03, 0x02, "CCU1"):
                 result["success"] = False
                 _log("CCU1 默认配置恢复失败")
            else:
                 _log("CCU1 默认配置恢复成功")

        # d) Delete Logs
        if options.get("delete_logs"):
            ssh_client = self._device_service.get_ssh_client()
            if ssh_client and ssh_client.is_connected():
                try:
                    _log("开始删除 DLT 日志文件...")
                    # d) 删除 /log 下所有日志文件
                    cmd = "rm -rf /log/*"
                    _log(f"执行 SSH 指令: {cmd}")
                    out = ssh_client.execute_command(cmd)
                    _log("日志删除指令已发送")
                except Exception as e:
                    _log(f"日志删除失败: {e}")
                    result["success"] = False
            else:
                _log("SSH 未连接，无法删除日志")
                result["success"] = False

        return result

    def _set_did_byte(self, did: int, val: int, ecu_name: str) -> bool:
        """Helper to set a single byte DID value via UDS."""
        _log = self.log_signal.emit

        doip_client = self._device_service.get_doip_client()
        if not doip_client:
             _log("DoIP 未连接")
             return False

        did_bytes = did.to_bytes(2, 'big')
        write_cmd = bytes([0x2E]) + did_bytes + bytes([val])

        is_factory_mode = False
        if self._topology_service:
            # Silence internal log? Or pass log_callback
            try:
                fm = self._topology_service._get_factory_mode()
                if "工厂模式" in fm: is_factory_mode = True
            except:
                pass

        _log(f"设置 DID {did:X} = {val:02X} , 发送UDS指令： {write_cmd.hex(' ').upper()}")

        if not is_factory_mode:
            resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_signal=self.log_signal)
        else:
            # 10 03
            self._device_service.send_doip_payload(bytes.fromhex("10 03"))
            resp = self._device_service.send_doip_payload(write_cmd)

        if resp and resp[0] == 0x6E:
             return True
        else:
             _log(f"设置失败, 响应: {resp.hex(' ') if resp else 'None'}")
             return False

    def _restore_ccua_default(self) -> bool:
        """
        a1) UDS 2E BE 17 02
        a2) Walk process_log_config.json via SSH
        """
        _log = self.log_signal.emit
        # a1) Update DID 0xBE17 to 02
        if not self._set_did_byte(0xBE17, 0x02, "CCUA"):
            return False

        # # a2) Restore process_log_configs
        # # Load local map file
        # # Use user provided path if available
        # if self._map_file_path and os.path.exists(self._map_file_path):
        #     map_file_path = self._map_file_path
        # else:
        #     _log("错误: 未设置本地映射文件路径，请在导入区域选择JSON文件")
        #     return False
        #
        # try:
        #     if not os.path.exists(map_file_path):
        #           _log(f"错误: 找不到映射文件 {map_file_path}")
        #           return False
        #
        #     _log(f"使用映射文件: {map_file_path}")
        #     with open(map_file_path, 'r', encoding='utf-8') as f:
        #         data = json.load(f)
        #         configs = data.get("process_log_configs", {})
        # except Exception as e:
        #     _log(f"无法读取映射文件: {e}")
        #     return False
        #
        # ssh_client = self._device_service.get_ssh_client()
        # if not ssh_client or not ssh_client.is_connected():
        #     _log("SSH 未连接，无法恢复 APP 配置文件")
        #     return False
        #
        # success_count = 0
        # fail_count = 0
        #
        # for key, info in configs.items():
        #     remote_path = info.get("path")
        #     if not remote_path: continue
        #
        #     # Read remote file
        #     cmd_read = f"cat {remote_path}"
        #     # _log(f"读取: {remote_path}")
        #     json_content_str = ssh_client.execute_command(cmd_read)
        #     if not json_content_str:
        #          # _log(f"读取失败或文件为空: {key}")
        #          fail_count += 1
        #          continue
        #
        #     try:
        #         remote_json = json.loads(json_content_str)
        #         modified = False
        #
        #         # Check logTraceLogLevel -> ERROR
        #         if remote_json.get("logTraceLogLevel") != "ERROR":
        #             remote_json["logTraceLogLevel"] = "ERROR"
        #             modified = True
        #
        #         # Check logTraceLogMode -> NETWORK
        #         if remote_json.get("logTraceLogMode") != "NETWORK":
        #             remote_json["logTraceLogMode"] = "NETWORK"
        #             modified = True
        #
        #         if modified:
        #             # Write back
        #             new_content = json.dumps(remote_json, indent=4)
        #             # Escape double quotes for shell command if simple echo used, or use sftp?
        #             # Using a safe write method is better.
        #             # Assuming ssh_client has capability to write file or use echo
        #
        #             # Trick: use echo '...' > path. Need to handle JSON quotes.
        #             # A safer way is using python on device if available, or just careful escaping.
        #             # Or 'cat > path <<EOF ... EOF'
        #
        #             # Let's try simple echo with single quotes wrapping json
        #             safe_json = new_content.replace("'", "'\\''") # Escape single quotes inside JSON
        #             cmd_write = f"echo '{safe_json}' > {remote_path}"
        #
        #             ssh_client.execute_command(cmd_write)
        #             # Verify? Skip for performance or do sample verification
        #             # _log(f"已恢复: {key}")
        #             success_count += 1
        #         else:
        #             # _log(f"无需修改: {key}")
        #             pass
        #
        #     except json.JSONDecodeError:
        #         # _log(f"JSON 解析失败: {remote_path}")
        #         fail_count += 1
        #         pass
        #     except Exception as e:
        #         # _log(f"处理失败 {key}: {e}")
        #         fail_count += 1
        #
        # _log(f"APP 配置恢复统计: 修改 {success_count}, 失败/跳过 {fail_count}")
        return True

    def reset_ccu(self):
        """UDS 11 03 (Soft Reset)"""
        _log = self.log_signal.emit

        _log("正在执行 CCU 软复位 (11 03)...")
        # 11 03 usually requires session?
        # Assuming Default session or Extended is fine. Usually hard reset needs 10 03?
        # Let's try directly or ensure session 01/03.
        # Most ECUs accept 11 01/03 in any session or extended.

        # Send 11 03
        cmd = bytes.fromhex("11 03")
        doip_client = self._device_service.get_doip_client()
        if doip_client:
             resp = doip_client.send_doip_message(cmd)
             if resp and (resp[0] == 0x51):
                 _log("CCU 复位指令发送成功")
                 return True
             else:
                 _log(f"CCU 复位失败: {resp.hex(' ') if resp else '无响应'}")
                 return False
        return False
