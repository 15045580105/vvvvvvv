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

    def inject_device_service(self, device_service: DeviceService):
        self._device_service = device_service
        # 注入 TopologyService，如果未注入则尝试从 DI 容器获取或创建
        self._topology_service = di_container.resolve(TopologyService)
        if not self._topology_service:
            self._topology_service = TopologyService(device_service)
            di_container.register_singleton(TopologyService, self._topology_service)

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

    def restore_config(self, restore_options: Dict[str, bool]) -> bool:
        """Restore default configuration."""
        print(f"Restoring config with options: {restore_options}")
        return True
