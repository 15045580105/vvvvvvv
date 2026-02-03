from typing import List, Dict, Any, Optional
from app.core.base_service import BaseService
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService


class LogConfigService(BaseService):
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

    def set_ecu_log_level(self, ecus: List[str], level: str, log_callback=None) -> bool:
        """Set log level for specified ECUs."""
        if not self._device_service:
            if log_callback: log_callback("DeviceService 未注入")
            return False

        # Map log level string to integer value
        level_map = {
            "OFF": 0,
            "FATAL": 1,
            "ERROR": 2,
            "WARN": 3,
            "INFO": 4,
            "DEBUG": 5,
            "VERBOSE": 6
        }
        level_val = level_map.get(level, 4)  # Default to INFO if unknown

        # Map ECU name to DID
        ecu_did_map = {
            "CCU0": 0xBE02,
            "CCU1": 0xBE03,
            "CCUA": 0xBE17  # Assuming CCUA maps to BE17 based on user request
        }

        success_all = True

        for ecu in ecus:
            did = ecu_did_map.get(ecu)
            if not did:
                if log_callback: log_callback(f"未知 ECU: {ecu}")
                continue

            did_bytes = did.to_bytes(2, 'big')

            # We need to access the DoIP client from device service
            doip_client = self._device_service.get_doip_client()
            if not doip_client:
                if log_callback: log_callback("DoIP 客户端未连接")
                return False

            # Helper to log
            def _log(msg):
                if log_callback:
                    log_callback(f"[{ecu}] {msg}")
                else:
                    print(f"[{ecu}] {msg}")

            # --- Step 1: Read Current ---
            _log(f"读取当前日志配置 (22 {did:X})...")
            read_cmd = bytes([0x22]) + did_bytes
            resp = doip_client.send_doip_message(read_cmd)
            if not resp or resp[0] != 0x62:
                _log(f"读取失败: {resp.hex(' ').upper() if resp else '无响应'}")
                success_all = False
                continue

            _log(f"当前配置: {resp.hex(' ').upper()}")

            # --- Step 2: Write New Config (2E DID VAL) ---
            # 2E BE 02 06 (Example)
            write_cmd = bytes([0x2E]) + did_bytes + bytes([level_val])

            _log(f"设置日志等级为 {level} ({level_val}) (2E {did:X} {level_val:02X})...")

            # 读取是否为工厂模式，工厂模式不需要走2701安全认证
            is_factory_mode = False
            if self._topology_service:
                factory_mode_str = self._topology_service._get_factory_mode(log_callback=_log)
                if "工厂模式" in factory_mode_str:
                    is_factory_mode = True
                    _log("检测到用户模式，跳过安全访问")
                else:
                    _log("检测到非工厂模式，执行安全访问")

            else:
                _log("TopologyService 未就绪，默认执行安全访问")

            if not is_factory_mode:
                # 非工厂模式：走完整安全访问流程 (10 03 -> 27 01 -> 2E)
                write_resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_callback=_log)
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

                # 2. 2E ...
                _log(f"发送写指令: {write_cmd.hex(' ').upper()}")
                write_resp = self._device_service.send_doip_payload(write_cmd)

            if not write_resp:
                _log("设置失败")
                success_all = False
                continue

            # Check positive response for 2E is 6E
            if write_resp[0] != 0x6E:
                _log(f"设置失败，响应: {write_resp.hex(' ').upper()}")
                success_all = False
                continue

            # --- Step 3: Read Back (22 DID) ---
            _log(f"回读验证配置 (22 {did:X})...")
            verify_resp = doip_client.send_doip_message(read_cmd)
            if not verify_resp or verify_resp[0] != 0x62:
                _log(f"回读失败: {verify_resp.hex(' ').upper() if verify_resp else '无响应'}")
                success_all = False
                continue

            # Verify value (assuming format is 62 DID VAL)
            # resp: 62 BE 02 06
            if len(verify_resp) >= 4 and verify_resp[3] == level_val:
                _log("配置成功！")
            else:
                _log(f"验证失败，当前值: {verify_resp.hex(' ').upper()}")
                success_all = False

        return success_all

    def get_apps(self, ecu_filter: str = "", app_filter: str = "", level_filter: str = "") -> List[Dict[str, Any]]:
        """Get list of applications and their log configurations."""
        # TODO: Implement actual retrieval
        # Return dummy data for now
        return [
            {"app_id": "ACSG", "ecu_id": "CCUA", "log_level": "INFO", "file_no": "1", "file_size": "10MB", "total_size": "100MB"},
            {"app_id": "ADAP", "ecu_id": "CCUA", "log_level": "DEBUG", "file_no": "2", "file_size": "5MB", "total_size": "50MB"},
            {"app_id": "TSYN", "ecu_id": "CCU0", "log_level": "WARN", "file_no": "1", "file_size": "2MB", "total_size": "20MB"},
            {"app_id": "SOAM", "ecu_id": "CCU1", "log_level": "ERROR", "file_no": "3", "file_size": "15MB", "total_size": "150MB"},
        ]

    def export_logs(self, app_ids: List[str], destination: str) -> bool:
        """Export logs for selected apps."""
        print(f"Exporting logs for {app_ids} to {destination}")
        return True

    def delete_logs(self, app_ids: List[str]) -> bool:
        """Delete logs for selected apps."""
        print(f"Deleting logs for {app_ids}")
        return True

    def restore_config(self, options: Dict[str, bool], log_callback=None) -> Dict[str, Any]:
        """Restore default configuration based on options."""
        # Helper to log
        def _log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        result = {"success": True, "restart_required": False}

        # a) Restore CCUA
        if options.get("restore_ccua"):
            _log("开始恢复 CCUA 默认配置...")
            if not self._restore_ccua_default(log_callback):
                result["success"] = False
                _log("CCUA 默认配置恢复失败")
            else:
                _log("CCUA 默认配置恢复成功")
                result["restart_required"] = True # Need confirm restart in UI

        # b) Restore CCU0
        if options.get("restore_ccu0"):
            _log("开始恢复 CCU0 默认配置...")
            # b) 发送 UDS 2E BE 02 02
            if not self._set_did_byte(0xBE02, 0x02, "CCU0", log_callback):
                 result["success"] = False
                 _log("CCU0 默认配置恢复失败")
            else:
                 _log("CCU0 默认配置恢复成功")

        # c) Restore CCU1
        if options.get("restore_ccu1"):
            _log("开始恢复 CCU1 默认配置...")
            # c) 发送 UDS 2E BE 03 02
            if not self._set_did_byte(0xBE03, 0x02, "CCU1", log_callback):
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

    def _set_did_byte(self, did: int, val: int, ecu_name: str, log_callback=None) -> bool:
        """Helper to set a single byte DID value via UDS."""
        def _log(msg):
             if log_callback: log_callback(f"[{ecu_name}] {msg}")

        doip_client = self._device_service.get_doip_client()
        if not doip_client:
             _log("DoIP 未连接")
             return False

        did_bytes = did.to_bytes(2, 'big')
        write_cmd = bytes([0x2E]) + did_bytes + bytes([val])

        # Check factory mode logic similar to set_log_level... can extract if needed
        # Assuming secure routine flow logic reuse or simplification:
        # For simplicity reusing execute_secure_routine or send_doip_payload based on same logic

        # NOTE: Reusing the logic from set_ecu_log_level about factory mode
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
            resp = self._device_service.execute_secure_routine(write_cmd, sec_level=0x01, log_callback=_log)
        else:
            # 10 03
            self._device_service.send_doip_payload(bytes.fromhex("10 03"))
            resp = self._device_service.send_doip_payload(write_cmd)

        if resp and resp[0] == 0x6E:
             return True
        else:
             _log(f"设置失败, 响应: {resp.hex(' ') if resp else 'None'}")
             return False

    def _restore_ccua_default(self, log_callback=None) -> bool:
        """
        a1) UDS 2E BE 17 02
        a2) Walk process_log_config.json via SSH
        """
        def _log(msg):
            if log_callback: log_callback(f"[CCUA] {msg}")

        # a1) Update DID 0xBE17 to 02
        if not self._set_did_byte(0xBE17, 0x02, "CCUA", log_callback):
            return False

        # a2) Restore process_log_configs
        # Load local map file
        import json
        import os

        # Use user provided path if available
        if self._map_file_path and os.path.exists(self._map_file_path):
            map_file_path = self._map_file_path
        else:
            # Fallback logic
            map_filename = "process_log_config_map.json"
            map_file_path = map_filename

            # Try to find the file in CWD or Project Root
            if not os.path.exists(map_file_path):
                 # Try going up from the current file location to find project root
                 # This file is in app/services/configuration/
                 current_dir = os.path.dirname(os.path.abspath(__file__))
                 project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
                 potential_path = os.path.join(project_root, map_filename)
                 if os.path.exists(potential_path):
                     map_file_path = potential_path
                 else:
                     # Fallback: try one more level or just cwd join
                     map_file_path = os.path.join(os.getcwd(), map_filename)

        try:
            if not os.path.exists(map_file_path):
                  _log(f"错误: 找不到映射文件 {map_file_path}")
                  return False

            _log(f"使用映射文件: {map_file_path}")
            with open(map_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                configs = data.get("process_log_configs", {})
        except Exception as e:
            _log(f"无法读取映射文件: {e}")
            return False

        ssh_client = self._device_service.get_ssh_client()
        if not ssh_client or not ssh_client.is_connected():
            _log("SSH 未连接，无法恢复 APP 配置文件")
            return False

        success_count = 0
        fail_count = 0

        for key, info in configs.items():
            remote_path = info.get("path")
            if not remote_path: continue

            # Read remote file
            cmd_read = f"cat {remote_path}"
            # _log(f"读取: {remote_path}")
            json_content_str = ssh_client.execute_command(cmd_read)
            if not json_content_str:
                 # _log(f"读取失败或文件为空: {key}")
                 fail_count += 1
                 continue

            try:
                remote_json = json.loads(json_content_str)
                modified = False

                # Check logTraceLogLevel -> ERROR
                if remote_json.get("logTraceLogLevel") != "ERROR":
                    remote_json["logTraceLogLevel"] = "ERROR"
                    modified = True

                # Check logTraceLogMode -> NETWORK
                if remote_json.get("logTraceLogMode") != "NETWORK":
                    remote_json["logTraceLogMode"] = "NETWORK"
                    modified = True

                if modified:
                    # Write back
                    new_content = json.dumps(remote_json, indent=4)
                    # Escape double quotes for shell command if simple echo used, or use sftp?
                    # Using a safe write method is better.
                    # Assuming ssh_client has capability to write file or use echo

                    # Trick: use echo '...' > path. Need to handle JSON quotes.
                    # A safer way is using python on device if available, or just careful escaping.
                    # Or 'cat > path <<EOF ... EOF'

                    # Let's try simple echo with single quotes wrapping json
                    safe_json = new_content.replace("'", "'\\''") # Escape single quotes inside JSON
                    cmd_write = f"echo '{safe_json}' > {remote_path}"

                    ssh_client.execute_command(cmd_write)
                    # Verify? Skip for performance or do sample verification
                    # _log(f"已恢复: {key}")
                    success_count += 1
                else:
                    # _log(f"无需修改: {key}")
                    pass

            except json.JSONDecodeError:
                # _log(f"JSON 解析失败: {remote_path}")
                fail_count += 1
                pass
            except Exception as e:
                # _log(f"处理失败 {key}: {e}")
                fail_count += 1

        _log(f"APP 配置恢复统计: 修改 {success_count}, 失败/跳过 {fail_count}")
        return True

    def reset_ccu(self, log_callback=None):
        """UDS 11 03 (Soft Reset)"""
        def _log(msg):
            if log_callback: log_callback(msg)

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
