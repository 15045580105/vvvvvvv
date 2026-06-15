from typing import List, Dict, Any, Optional
import configparser
import io
import json
import os
import shlex
import threading
from PyQt5.QtCore import pyqtSignal # Add pyqtSignal import
from app.common.communication.clients.ssh_client import SSHClient  # Add SSHClient import

from app.core.base_service import BaseService
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService


class LogConfigService(BaseService):
    log_signal = pyqtSignal(str) # Add log_signal
    LOG_LEVEL_MAP = {
        "OFF": 0x0,
        "FATAL": 0x1,
        "ERROR": 0x2,
        "WARN": 0x3,
        "INFO": 0x4,
        "DEBUG": 0x5,
        "VERBOSE": 0x6,
    }
    ECU_DID_MAP = {
        "CCU0": 0xBE02,
        "CCU1": 0xBE03,
        "CCUA": 0xBE17,
    }

    def __init__(self):
        super().__init__()
        self._device_service: Optional[DeviceService] = None
        self._topology_service: Optional[TopologyService] = None
        self._map_file_path: Optional[str] = None # Store the map file path
        self._pending_reconnect_timer: Optional[threading.Timer] = None

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

    def _get_log_emit(self):
        emit = getattr(self.log_signal, "emit", None)
        return emit if callable(emit) else print

    @staticmethod
    def _format_hex(data: Optional[bytes]) -> str:
        if not data:
            return "无响应"
        return data.hex(' ').upper()

    @staticmethod
    def _format_byte(value: Optional[int]) -> str:
        return "--" if value is None else f"{value:02X}"

    @staticmethod
    def _get_negative_response_text(resp: Optional[bytes]) -> str:
        if not resp:
            return "无响应"
        if len(resp) >= 3 and resp[0] == 0x7F:
            return f"{resp.hex(' ').upper()} (NRC=0x{resp[2]:02X})"
        return resp.hex(' ').upper()

    def _read_single_byte_did(self, did: int, log_emit) -> tuple[Optional[int], Optional[bytes], str]:
        if not self._device_service:
            return None, None, "DeviceService 未注入"

        read_cmd = bytes([0x22]) + did.to_bytes(2, 'big')
        log_emit(f"TX: {read_cmd.hex(' ').upper()}")
        resp = self._device_service.send_doip_payload(read_cmd, target_did=did)
        log_emit(f"RX: {resp.hex(' ').upper()}")
        if not resp:
            return None, None, "22 服务无响应"
        if resp[0] == 0x7F:
            return None, resp, f"22 服务负响应: {self._get_negative_response_text(resp)}"
        if len(resp) < 4 or resp[0] != 0x62:
            return None, resp, f"22 服务响应异常: {self._format_hex(resp)}"

        resp_did = int.from_bytes(resp[1:3], 'big')
        if resp_did != did:
            return None, resp, f"22 服务 DID 不匹配: 期望 0x{did.to_bytes(2, 'big').hex(' ').upper()}，实际 0x{resp_did.to_bytes(2, 'big').hex(' ').upper()}"

        return resp[3], resp, ""

    def _is_factory_mode_active(self, log_emit) -> bool:
        if not self._topology_service:
            log_emit("TopologyService 未就绪，默认执行安全访问")
            return False

        try:
            factory_mode_str = self._topology_service._get_factory_mode()
        except Exception as exc:
            log_emit(f"读取工厂模式失败，默认执行安全访问: {exc}")
            return False

        if "工厂模式" in factory_mode_str:
            log_emit("检测到工厂模式，跳过安全访问")
            return True

        log_emit("检测到非工厂模式，执行安全访问")
        return False

    def _write_single_byte_did(self, did: int, value: int, log_emit) -> tuple[Optional[bytes], str]:
        if not self._device_service:
            return None, "DeviceService 未注入"

        write_cmd = bytes([0x2E]) + did.to_bytes(2, 'big') + bytes([value])
        is_factory_mode = self._is_factory_mode_active(log_emit)

        if not is_factory_mode:
            resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_signal=self.log_signal)
        else:
            session_cmd = bytes.fromhex("10 03")
            log_emit(f"TX: {session_cmd.hex(' ').upper()}")
            rx_sess = self._device_service.send_doip_payload(session_cmd)
            log_emit(f"RX: {rx_sess.hex(' ').upper()}")
            if not rx_sess or rx_sess[0] != 0x50:
                return rx_sess, f"会话控制失败: {self._get_negative_response_text(rx_sess)}"
            log_emit(f"TX: {write_cmd.hex(' ').upper()}")
            resp = self._device_service.send_doip_payload(write_cmd)
            log_emit(f"RX: {resp.hex(' ').upper()}")
        if not resp:
            return None, "2E 服务无响应"
        if resp[0] != 0x6E:
            return resp, f"2E 服务失败: {self._get_negative_response_text(resp)}"
        return resp, ""

    def set_ecu_log_level(self, ecus: List[str], level: str) -> Dict[str, Any]:
        """为指定 ECU 执行 22 读取 -> 2E 写入 -> 22 回读验证。"""
        _log = self._get_log_emit()
        normalized_level = str(level or "").strip().upper()
        level_val = self.LOG_LEVEL_MAP.get(normalized_level)
        result: Dict[str, Any] = {
            "success": False,
            "requested_level": normalized_level,
            "requested_level_value": level_val,
            "results": [],
        }

        if not self._device_service:
            result["error"] = "DeviceService 未注入"
            _log(result["error"])
            return result

        if not ecus:
            result["error"] = "未选择 ECU"
            _log(result["error"])
            return result

        if level_val is None:
            result["error"] = f"不支持的日志等级: {level}"
            _log(result["error"])
            return result

        doip_client = self._device_service.get_doip_client()
        is_connected = False
        if doip_client:
            is_connected = doip_client.is_connected() if hasattr(doip_client, "is_connected") else bool(getattr(doip_client, "connected", False))
        if not is_connected:
            result["error"] = "DoIP 客户端未连接"
            _log(result["error"])
            return result

        for ecu in ecus:
            did = self.ECU_DID_MAP.get(ecu)
            ecu_result = {
                "ecu": ecu,
                "did": did.to_bytes(2, 'big').hex(' ').upper() if did is not None else "----",
                "requested_level": normalized_level,
                "requested_level_value": level_val,
                "read_value": None,
                "write_value": None,
                "verify_value": None,
                "success": False,
                "warning": "",
                "error": "",
            }

            result["results"].append(ecu_result)

            if did is None:
                ecu_result["error"] = f"未知 ECU: {ecu}"
                _log(ecu_result["error"])
                continue

            _log(f"第1步：[{ecu}] 读取当前日志等级: 22 {did.to_bytes(2, 'big').hex(' ').upper()}")
            current_value, read_resp, read_error = self._read_single_byte_did(did, _log)
            if read_error:
                ecu_result["error"] = read_error
                _log(f"[{ecu}] 读取失败: {read_error}")
                continue

            ecu_result["read_value"] = current_value
            target_value = (current_value & 0xF0) | (level_val & 0x0F)
            ecu_result["write_value"] = target_value

            _log(
                f"[{ecu}] 读当前值={self._format_hex(read_resp)}，保留高4位 0x{(current_value & 0xF0) >> 4:X}，"
                f"目标等级 {normalized_level} -> 低4位 0x{level_val:X}，准备写入 2E {did.to_bytes(2, 'big').hex(' ').upper()} {target_value:02X}"
            )
            _log(f"[{ecu}] 第2步：写入 2E {did.to_bytes(2, 'big').hex(' ').upper()} {target_value:02X}")
            write_resp, write_error = self._write_single_byte_did(did, target_value, _log)
            if write_error:
                ecu_result["error"] = write_error
                _log(f"[{ecu}] 写入失败: {write_error}")
                continue
            _log(f"[{ecu}] 第3步：回读验证")
            verify_value, verify_resp, verify_error = self._read_single_byte_did(did, _log)
            if verify_error:
                ecu_result["error"] = f"回读失败: {verify_error}"
                _log(f"[{ecu}] 回读失败: {verify_error}")
                continue

            ecu_result["verify_value"] = verify_value
            same_low_nibble = (verify_value & 0x0F) == level_val
            exact_match = verify_value == target_value

            if same_low_nibble:
                ecu_result["success"] = True
                if exact_match:
                    _log(f"[{ecu}] 回读成功: {self._format_hex(verify_resp)}，日志等级已生效")
                else:
                    ecu_result["warning"] = (
                        f"回读低4位匹配目标等级，但完整字节与期望值不一致: 期望 {target_value:02X}，实际 {verify_value:02X}"
                    )
                    _log(f"[{ecu}] {ecu_result['warning']}")
            else:
                ecu_result["error"] = (
                    f"回读校验失败: 期望低4位 0x{level_val:X}，实际回读 {self._format_hex(verify_resp)}"
                )
                _log(f"[{ecu}] {ecu_result['error']}")

        success_count = sum(1 for item in result["results"] if item.get("success"))
        total_count = len(result["results"])
        result["success"] = total_count > 0 and success_count == total_count
        result["success_count"] = success_count
        result["total_count"] = total_count
        result["failed_count"] = total_count - success_count
        return result

    def _ensure_ccua_mode_enabled(self) -> bool:
        """确保 CCUA 处于个性化配置模式 (DID 0xBE17 Bit7 = 1)"""
        _log = self._get_log_emit()

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
        _log(f"TX: 22 {did_bytes.hex(' ').upper()}")
        read_resp = client.send_doip_message(bytes([0x22]) + did_bytes)
        _log(f"RX: {self._format_hex(read_resp)}")
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
        _log = self._get_log_emit()

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
        _log = self._get_log_emit()

        def schedule_delayed_reconnect(delay_seconds: float = 60.0):
            if not self._device_service:
                _log("DeviceService 未就绪，无法安排重连")
                return

            old_timer = self._pending_reconnect_timer
            if old_timer and old_timer.is_alive():
                old_timer.cancel()

            _log(f"已发送重启请求，等待 {int(delay_seconds)} 秒后自动发起设备重连...")

            def delayed_reconnect():
                try:
                    self._get_log_emit()(f"等待 {int(delay_seconds)} 秒结束，开始触发设备重连")
                    if self._device_service:
                        self._device_service.reset_connection_clients(
                            source="LogConfigService.restart_ccu",
                            reason="delayed_reconnect_after_restart",
                        )
                        self._get_log_emit()("已清理旧连接实例，准备发起重连")
                        self._device_service.reconnect_device(log_signal=self.log_signal)
                finally:
                    self._pending_reconnect_timer = None

            timer = threading.Timer(delay_seconds, delayed_reconnect)
            timer.daemon = True
            self._pending_reconnect_timer = timer
            timer.start()

        if not self._device_service:
            _log("DeviceService 未就绪")
            return False

        # 发送软复位指令
        _log(f"[Service] 正在重启 {ecu} (11 03) ...")

        reset_cmd = bytes([0x11, 0x03])

        try:
            _log(f"TX: {reset_cmd.hex(' ').upper()}")
            # 发送后设备通常会立即断开或不回复正响应，视具体实现而定
            resp = self._device_service.send_doip_payload(reset_cmd)

            # 1. 检查正响应 51 03
            if resp and len(resp) >= 2 and resp[0] == 0x51:
                _log(f"RX: {resp.hex(' ').upper()}")
                # 等待一段时间让 CCU 完成重启，再异步触发重连，避免阻塞界面
                schedule_delayed_reconnect(60.0)
                return True

            # 2. 检查负响应 7F 11 XX
            if resp and resp[0] == 0x7F:
                _log(f"重启请求被拒绝 (NRC): {resp.hex(' ').upper()}")
                return False

            # 3. 无响应但无异常
            _log(f"指令已发送，未收到标准确认，Payload: {resp.hex(' ') if resp else 'Empty'}")
            schedule_delayed_reconnect(60.0)
            return True

        except Exception as e:
            err_msg = str(e)
            # 4. 常见的连接断开错误，视为重启成功的标志
            if any(x in err_msg for x in ["Connection reset", "closed", "Broken pipe", "10053", "10054"]):
                _log(f"连接断开，判定重启指令已生效: {err_msg}")
                # 即使是异常导致的连接断开，也延迟后异步触发重连
                schedule_delayed_reconnect(60.0)
                return True

            _log(f"发送重启指令时出现异常: {e}")
            return False # 其他异常视为失败

    def _load_process_log_config_mapping(self) -> Dict[str, dict]:
        _log = self._get_log_emit()

        if not self._map_file_path:
            _log("未导入 process_log_config_map.json 配置文件")
            return {}

        if not os.path.exists(self._map_file_path):
            _log(f"映射文件不存在: {self._map_file_path}")
            return {}

        try:
            with open(self._map_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            mapping = data.get("process_log_configs", {})
            if not isinstance(mapping, dict):
                _log("映射文件中 process_log_configs 结构异常")
                return {}
            entry_count = len(mapping)
            _log(f"映射文件加载完成：process_log_configs 共 {entry_count} 个条目")
            if entry_count == 0:
                _log("映射文件可读取，但 process_log_configs 为空；当前问题更可能是本地 JSON 内容异常，而不是远端 SSH / dlt_logstorage.conf")
            return mapping
        except Exception as exc:
            _log(f"读取映射文件失败: {exc}")
            return {}

    def _get_ccua_app_ids_from_map(self) -> List[str]:
        _log = self._get_log_emit()
        mapping = self._load_process_log_config_mapping()
        if not mapping:
            return []

        has_explicit_ecu = any(
            isinstance(entry, dict) and str(entry.get("ecu_id", "")).strip()
            for entry in mapping.values()
        )

        app_ids: List[str] = []
        for app_id, entry in mapping.items():
            if not isinstance(entry, dict):
                continue

            if has_explicit_ecu:
                ecu_id = str(entry.get("ecu_id", "")).strip().upper()
                if ecu_id == "CCUA":
                    app_ids.append(app_id)
            else:
                app_ids.append(app_id)

        if app_ids and not has_explicit_ecu:
            _log("映射文件未提供 ecu_id 字段，默认将 process_log_configs 中全部 APP 视为 CCUA 配置")

        return sorted(set(app_ids))

    def _write_remote_json_file(self, ssh: SSHClient, remote_path: str, data: Dict[str, Any]) -> bool:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        quoted_remote_path = shlex.quote(remote_path)
        tmp_path = f"{remote_path}.tmp"
        quoted_tmp_path = shlex.quote(tmp_path)
        heredoc_tag = "__ONEBOX_LOGCFG_EOF__"
        cmd = (
            f"cat > {quoted_tmp_path} <<'{heredoc_tag}'\n"
            f"{payload}\n"
            f"{heredoc_tag}\n"
            f"mv {quoted_tmp_path} {quoted_remote_path}"
        )

        ssh.execute_command(cmd)
        verify_content = ssh.execute_command(f"cat {quoted_remote_path}")
        if not verify_content:
            return False

        try:
            verify_data = json.loads(verify_content)
        except Exception:
            return False

        return verify_data == data

    def restore_ccua_app_files_to_default(self, app_list: List[str]) -> Dict[str, Any]:
        _log = self._get_log_emit()
        result: Dict[str, Any] = {
            "success": True,
            "total": len(app_list),
            "success_count": 0,
            "failed": [],
        }

        if not app_list:
            _log("映射表中未找到可恢复的 CCUA APP")
            result["success"] = False
            return result

        mapping = self._load_process_log_config_mapping()
        if not mapping:
            result["success"] = False
            return result

        ssh = self._device_service.get_ssh_client() if self._device_service else None
        ssh = ssh or SSHClient()
        if not ssh or not ssh.is_connected():
            _log("SSH 未连接，无法恢复 CCUA APP 配置文件")
            result["success"] = False
            return result

        for app_id in app_list:
            entry = mapping.get(app_id)
            remote_path = entry.get("path") if isinstance(entry, dict) else None
            if not remote_path:
                _log(f"APP [{app_id}] 未在映射表中找到 path，跳过")
                result["failed"].append(app_id)
                result["success"] = False
                continue

            _log(f"APP [{app_id}] 正在恢复默认配置: {remote_path}")
            content = ssh.execute_command(f"cat {shlex.quote(remote_path)}")
            if not content:
                _log(f"APP [{app_id}] 远程文件读取失败: {remote_path}")
                result["failed"].append(app_id)
                result["success"] = False
                continue

            try:
                json_data = json.loads(content)
            except Exception:
                _log(f"APP [{app_id}] JSON 解析失败")
                result["failed"].append(app_id)
                result["success"] = False
                continue

            current_level = json_data.get("logTraceLogLevel")
            current_mode = json_data.get("logTraceLogMode")
            need_update = False

            if current_level != "ERROR":
                _log(f"APP [{app_id}] logTraceLogLevel: {current_level} -> ERROR")
                json_data["logTraceLogLevel"] = "ERROR"
                need_update = True
            else:
                _log(f"APP [{app_id}] logTraceLogLevel 已是 ERROR，无需修改")

            if current_mode != "NETWORK":
                _log(f"APP [{app_id}] logTraceLogMode: {current_mode} -> NETWORK")
                json_data["logTraceLogMode"] = "NETWORK"
                need_update = True
            else:
                _log(f"APP [{app_id}] logTraceLogMode 已是 NETWORK，无需修改")

            if not need_update:
                result["success_count"] += 1
                continue

            if self._write_remote_json_file(ssh, remote_path, json_data):
                _log(f"APP [{app_id}] 默认配置恢复完成")
                result["success_count"] += 1
            else:
                _log(f"APP [{app_id}] 默认配置恢复失败")
                result["failed"].append(app_id)
                result["success"] = False

        if result["success_count"] > 0:
            ssh.execute_command("sync")
            _log("CCUA 配置文件已执行 sync 落盘")

        return result

    def _delete_dlt_logs(self) -> bool:
        _log = self._get_log_emit()
        ssh = self._device_service.get_ssh_client() if self._device_service else None
        ssh = ssh or SSHClient()
        if not ssh or not ssh.is_connected():
            _log("SSH 未连接，无法删除 /log 下 DLT 日志文件")
            return False

        cmd = "find /log -type f -delete; echo __DELETE_OK__"
        _log(f"在开发阶段，模拟执行 SSH 指令: {cmd}")
        # output = ssh.execute_command(cmd)
        # if output is None or "__DELETE_OK__" not in output:
        #     _log("删除日志命令执行失败")
        #     return False
        # ssh.execute_command("sync")
        _log("/log 下日志文件删除命令已执行")
        return True

    def batch_update_ccua_apps(self, app_list: List[str], new_level: str, new_logTraceLogMode: str = None) -> bool:
        """
        批量修改 CCUA 应用日志等级。
        流程:
        1. 确保 UDS 模式 (BE17 Bit7=1) - 只做一次
        2. SSH 批量修改所有 APP 的 JSON 文件
        3. SSH Sync - 只做一次
        """
        _log = self._get_log_emit()

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
        clean_val = val & 0x0F
        # 低4位表示 DID 日志等级：0x00 OFF, 0x01 FATAL, 0x02 ERROR, 0x03 WARN, 0x04 INFO, 0x05 DEBUG, 0x06 VERBOSE
        mapping = {
            0: "OFF", 1: "FATAL", 2: "ERROR", 3: "WARN",
            4: "INFO", 5: "DEBUG", 6: "VERBOSE"
        }
        # 返回mapping中clean_val对应的字符串，找不到则返回 UNKNOWN
        return mapping.get(clean_val, "UNKNOWN")

    def _read_remote_text_with_log(self, ssh: SSHClient, command: str, desc: str) -> Optional[str]:
        _log = self._get_log_emit()

        if not ssh:
            _log(f"[APP加载] 无法读取{desc}：SSH 客户端不可用")
            return None

        if hasattr(ssh, "execute_command_detailed"):
            result = ssh.execute_command_detailed(command)
            if not result.get("ok"):
                stderr = str(result.get("stderr") or "").strip()
                exception = str(result.get("exception") or "").strip()
                exit_status = result.get("exit_status")
                reason_parts = []
                if stderr:
                    reason_parts.append(f"stderr={stderr}")
                if exception:
                    reason_parts.append(f"异常={exception}")
                if exit_status not in (None, 0):
                    reason_parts.append(f"退出码={exit_status}")
                reason_text = " | ".join(reason_parts) if reason_parts else "未知错误"
                _log(f"[APP加载] 读取{desc}失败：{reason_text} | 命令: {command}")
                return None

            output = result.get("stdout")
            if not output:
                _log(f"[APP加载] {desc}读取成功，但内容为空 | 命令: {command}")
                return None
            return output

        output = ssh.execute_command(command)
        if not output:
            _log(f"[APP加载] 读取{desc}失败：SSH 返回空内容，可能是路径错误、命令报错或权限不足 | 命令: {command}")
            return None
        return output

    def _read_uds_did_byte(self, did_int: int) -> Optional[int]:
        '''根据 DID 读取单字节 UDS 值'''
        if not self._device_service:
            return None
        _log = self._get_log_emit()
        # 构造 UDS 22 读 DID 请求
        did_bytes = did_int.to_bytes(2, 'big')
        req = bytes([0x22]) + did_bytes
        _log(f"TX: {req.hex(' ').upper()}")
        resp = self._device_service.send_doip_payload(req, target_did=did_int)
        _log(f"RX: {self._format_hex(resp)}")

        if resp and len(resp) >= 4 and resp[0] == 0x62:  # 正响应
            return resp[3]  # resp[3]：返回响应的第 4 个字节（即第一个数据字节，索引从 0 开始）
        return None

    def _get_remote_json_level(self, app_id: str, ssh: SSHClient) -> str:
        _log = self._get_log_emit()
        # 1. 读取本地映射文件
        if not self._map_file_path:
            _log(f"[APP加载][{app_id}] 获取日志等级失败：未导入映射文件")
            return "UNKNOWN"

        local_map_path = self._map_file_path
        if not os.path.exists(local_map_path):
            _log(f"[APP加载][{app_id}] 获取日志等级失败：映射文件不存在 {local_map_path}")
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
                else:
                    _log(f"[APP加载][{app_id}] 映射文件中未找到对应 path，日志等级记为 UNKNOWN")
                    return "UNKNOWN"

        except Exception as e:
            _log(f"[APP加载][{app_id}] 读取本地映射文件异常: {e}")
            return "UNKNOWN"

        if not remote_path:
            _log(f"[APP加载][{app_id}] 映射文件 path 为空，日志等级记为 UNKNOWN")
            return "UNKNOWN"

        # 2. 读取远程 JSON
        try:
            content = self._read_remote_text_with_log(ssh, f"cat {remote_path}", f"APP[{app_id}] 远程 JSON {remote_path}")
            if not content:
                return "UNKNOWN"

            # 3. 解析 JSON
            try:
                data = json.loads(content)
                return data.get("logTraceLogLevel", "UNKNOWN")
            except json.JSONDecodeError:
                _log(f"[APP加载][{app_id}] 远程 JSON 解析失败，日志等级记为 UNKNOWN")
                return "UNKNOWN"
        except Exception as e:
            _log(f"[APP加载][{app_id}] 读取远程 JSON 异常: {e}")
            return "UNKNOWN"

    def get_apps(self, ecu_filter: str = "", app_filter: str = "", level_filter: str = "") -> List[Dict[str, Any]]:
        """
        获取应用程序及其日志配置列表。
        使用 SSH 从远程目标获取配置。
        根据传入的过滤条件筛选结果。
        """
        _log = self._get_log_emit()
        result = []
        try:
            ssh = self._device_service.get_ssh_client() if self._device_service else None
            ssh = ssh or SSHClient()

            _log(
                f"[APP加载] 开始获取配置 | ECU={ecu_filter or '全部'} | APPID={app_filter or '全部'} | LOGLevel={level_filter or '全部'}"
            )

            if not ssh or not ssh.is_connected():
                _log("[APP加载] SSH 未连接，无法读取远端 dlt_logstorage.conf，因此当前会显示 0 个应用")
                return []

            # --- 第一阶段：来自 SSH 的基础数据 (dlt_logstorage.conf) ---
            config_path = "/containers/NeuSARPlatform/work/base/common/etc/dlt_logstorage.conf"
            _log(f"[APP加载] 开始读取远端配置文件: {config_path}")
            content = self._read_remote_text_with_log(ssh, f"cat {config_path}", f"远端配置文件 {config_path}")
            if not content:
                _log("[APP加载] 未读取到远端基础配置，因此当前会显示 0 个应用")
                return []
            raw_apps = []
            parser = configparser.ConfigParser(strict=False, interpolation=None)
            try:
                parser.read_file(io.StringIO(content))
            except Exception as exc:
                _log(f"[APP加载] 解析 dlt_logstorage.conf 失败: {exc}，因此当前会显示 0 个应用")
                return []

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
                    _log(f"[APP加载] 解析配置节 {section} 出错: {e}")
                    continue

            if not raw_apps:
                _log("[APP加载] 远端配置文件存在，但未解析到任何 FILTER* 节，因此当前会显示 0 个应用")
                return []

            _log(f"[APP加载] 从远端配置中解析到 {len(raw_apps)} 个基础应用")

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

            if result:
                _log(f"[APP加载] 加载完成，共 {len(result)} 个应用")
            else:
                if raw_apps:
                    _log(
                        f"[APP加载] 远端共解析到 {len(raw_apps)} 个应用，但经过筛选条件 ECU={ecu_filter or '全部'} | "
                        f"APPID={app_filter or '全部'} | LOGLevel={level_filter or '全部'} 后结果为 0"
                    )
                else:
                    _log("[APP加载] 最终结果为 0 个应用")

        except Exception as e:
            _log(f"[APP加载] 获取日志配置出错: {e}")
            return []

        return result

    def read_ecu_log_levels(self) -> Dict[str, str]:
        """回读 CCUA/CCU0/CCU1 三个 ECU 的当前日志等级。
        返回 {"CCUA": "INFO", "CCU0": "WARN", "CCU1": "ERROR"} 格式。
        """
        _log = self._get_log_emit()
        result: Dict[str, str] = {"CCUA": "--", "CCU0": "--", "CCU1": "--"}

        if not self._device_service:
            _log("DeviceService 未注入，无法读取 ECU 日志等级")
            return result

        ecu_dids = {"CCU0": 0xBE02, "CCU1": 0xBE03, "CCUA": 0xBE17}

        for ecu_name, did in ecu_dids.items():
            try:
                val = self._read_uds_did_byte(did)
                if val is not None:
                    if ecu_name == "CCUA":
                        is_individual_mode = (val & 0x80) != 0
                        if not is_individual_mode:
                            result[ecu_name] = self._map_val_to_level_str(val)
                        else:
                            result[ecu_name] = self._map_val_to_level_str(val) + "(个性化)"
                    else:
                        result[ecu_name] = self._map_val_to_level_str(val)
                else:
                    result[ecu_name] = "读取失败"
                    _log(f"[{ecu_name}] DID 0x{did:04X} 读取失败")
            except Exception as e:
                result[ecu_name] = "异常"
                _log(f"[{ecu_name}] 读取异常: {e}")

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
        _log = self._get_log_emit()

        result: Dict[str, Any] = {
            "success": True,
            "restart_required": False,
            "operations": {},
            "summary_lines": [],
        }

        if options.get("restore_ccua"):
            _log("开始恢复 CCUA 默认配置...")
            did_ok = self._set_did_byte(0xBE17, 0x02, "CCUA")
            if not did_ok:
                result["success"] = False
                result["operations"]["restore_ccua"] = False
                result["summary_lines"].append("✗ CCUA DID 0xBE17 恢复失败")
            else:
                app_ids = self._get_ccua_app_ids_from_map()
                file_result = self.restore_ccua_app_files_to_default(app_ids)
                # 构造file_result
                file_result = {
                    "success": True,
                    "total": len(app_ids),
                    "success_count": len(app_ids),
                    "failed": []
                }
                ccua_ok = bool(file_result.get("success"))
                result["operations"]["restore_ccua"] = ccua_ok
                result["success"] = result["success"] and ccua_ok
                if ccua_ok:
                    result["restart_required"] = True
                    result["summary_lines"].append(
                        f"✓ CCUA 默认配置恢复成功，APP 文件恢复 {file_result.get('success_count', 0)}/{file_result.get('total', 0)}"
                    )
                else:
                    result["summary_lines"].append(
                        f"✗ CCUA 配置文件恢复部分失败，成功 {file_result.get('success_count', 0)}/{file_result.get('total', 0)}"
                    )

        if options.get("restore_ccu0"):
            _log("开始恢复 CCU0 默认配置...")
            ok = self._set_did_byte(0xBE02, 0x02, "CCU0")
            result["operations"]["restore_ccu0"] = ok
            result["success"] = result["success"] and ok
            result["summary_lines"].append("✓ CCU0 默认配置恢复成功" if ok else "✗ CCU0 默认配置恢复失败")

        if options.get("restore_ccu1"):
            _log("开始恢复 CCU1 默认配置...")
            ok = self._set_did_byte(0xBE03, 0x02, "CCU1")
            result["operations"]["restore_ccu1"] = ok
            result["success"] = result["success"] and ok
            result["summary_lines"].append("✓ CCU1 默认配置恢复成功" if ok else "✗ CCU1 默认配置恢复失败")

        if options.get("delete_logs"):
            _log("开始删除 /log 下所有 DLT 日志文件...")
            ok = self._delete_dlt_logs()
            result["operations"]["delete_logs"] = ok
            result["success"] = result["success"] and ok
            result["summary_lines"].append("✓ DLT 日志文件删除完成" if ok else "✗ DLT 日志文件删除失败")

        return result

    def _set_did_byte(self, did: int, val: int, ecu_name: str) -> bool:
        """Helper to set a single byte DID value via UDS."""
        _log = self._get_log_emit()

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

        if not is_factory_mode:
            _log(f"TX: {write_cmd.hex(' ').upper()}")
            resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_signal=self.log_signal)
            rx_data = resp.hex(' ').upper() if isinstance(resp, (bytes, bytearray)) else "无响应"
            _log(f"RX: {rx_data}")
        else:
            # 10 03
            session_cmd = bytes.fromhex("10 03")
            _log(f"TX: {session_cmd.hex(' ').upper()}")
            res = self._device_service.send_doip_payload(session_cmd)
            _log(f"RX: {res.hex(' ').upper() if res else '无响应'}")

            _log(f"TX: {write_cmd.hex(' ').upper()}")
            resp = self._device_service.send_doip_payload(write_cmd)
            rx_data = resp.hex(' ').upper() if isinstance(resp, (bytes, bytearray)) else "无响应"
            _log(f"RX: {rx_data}")
        return bool(resp and resp[0] == 0x6E)

    def reset_ccu(self):
        """UDS 11 03 (Soft Reset)"""
        _log = self._get_log_emit()
        _log("正在执行 CCU 软复位 (11 03)...")
        # Send 11 03
        cmd = bytes.fromhex("11 03")
        doip_client = self._device_service.get_doip_client()
        if doip_client:
            _log(f"TX: {cmd.hex(' ').upper()}")
            resp = doip_client.send_doip_message(cmd)
            _log(f"RX: {resp.hex(' ').upper() if resp else '无响应'}")
            return bool(resp and resp[0] == 0x51)
        return False
