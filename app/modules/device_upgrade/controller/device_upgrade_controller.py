import os
import datetime
import json
import binascii
import time
import hashlib
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

from app.core.base_controller import BaseController
from app.modules.device_upgrade.model.device_upgrade_model import UpgradeModel
from app.modules.device_upgrade.view.device_upgrade_view import UpgradeView
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.common.utils.security_access_helper import SecurityAccessHelper
from app.common.utils.path_utils import get_app_data_path
from app.common.log.operation_log_manager import OperationLogManager
from app.common.utils.dpt_manager import DPTManager
from app.common.repositories.dpt_repository import DPTRepository


class UpgradeWorker(QThread):
    progress_signal = pyqtSignal(int, str, str) # percent, phase, log_msg
    log_signal = pyqtSignal(str, bool) # message, is_info
    finished_signal = pyqtSignal(bool, str) # success, message

    def __init__(self, config, file_path, device_service):
        super().__init__()
        self.config = config
        self.file_path = file_path
        self.device_service = device_service
        self.running = True
        self.dpt_manager = None

    def run(self):
        try:
            self._execute_upgrade()
        except Exception as e:
            self.log_signal.emit(f"升级流程异常: {str(e)}", True)
            self.finished_signal.emit(False, str(e))

    def stop(self):
        self.running = False

    def _wait_for_ecu_ready(self):
        self.log_signal.emit("正在轮询检测并等待 ECU 网络重连与诊断服务就绪...", True)
        wait_start = time.time()
        timeout = 60 # 最大等待60秒
        
        while self.running and (time.time() - wait_start) < timeout:
            doip_client = self.device_service.get_doip_client()
            if doip_client and doip_client.connected:
                try:
                    # 使用进入默认会话(10 01)试探ECU是否已经能处理诊断请求，并打印收发日志
                    payload = bytes([0x10, 0x01])
                    # 直接调用 _send_doip 以输出试探日志。暂存原有expect_positive以防失败强制退出
                    resp = self._send_doip(payload, "试探 ECU 默认会话是否能建立连接")
                    if resp and len(resp) > 0:
                         self.log_signal.emit("ECU 诊断服务已就绪，准备开始升级", True)
                         return True
                except:
                    pass
            time.sleep(1)
            
        self.log_signal.emit("警告: 等待 ECU 就绪超时，尝试强制继续...", True)
        return False

    def _execute_upgrade(self):
        # Load DPT Data for status check
        try:
            repo = DPTRepository()
            last_path = repo.load_last_path()
            if last_path and os.path.exists(last_path):
                 self.dpt_manager = DPTManager()
                 self.dpt_manager.load_dpt_from_file(last_path)
        except:
             pass

        file_size = os.path.getsize(self.file_path)
        file_hash = hashlib.sha256()

        # Phase constants
        PHASE_PREP = "PREP"
        PHASE_DOWNLOAD = "DOWNLOAD"
        PHASE_INSTALL = "INSTALL"

        self.log_signal.emit(f"开始升级流程, 文件: {os.path.basename(self.file_path)}, 大小: {file_size} bytes", True)

        # 0. Wait for ECU Ready Phase (轮询等待复位和重连完成)
        self._wait_for_ecu_ready()

        # Retrieve package config early
        pkg_config = {}
        if "package" in self.config and len(self.config["package"]) > 0:
            pkg_config = self.config["package"][0]

        # 1. Read DIDs (Sequence based on 1111.asc)
        # Sequence: F17F -> F180 -> F187 -> F189

        # F17F - ECU Hardware Version
        resp = self._send_uds("22 F1 7F", "申请读取ECU硬件版本号", PHASE_PREP, expect_positive=True, return_data=True)
        if resp:
            val = self._parse_did_string(resp)
            self.log_signal.emit(f"读取结果ECU硬件版本号：{val}", True)

        # F180 - Boot Software Version
        resp = self._send_uds("22 F1 80", "申请读取ECU Boot软件版本号", PHASE_PREP, expect_positive=True, return_data=True)
        if resp:
            val = self._parse_did_string(resp)
            self.log_signal.emit(f"读取结果ECU Boot软件版本号：{val}", True)

        # F187 - Part Number (Validate if in config)
        resp = self._send_uds("22 F1 87", "申请读取零件号", PHASE_PREP, expect_positive=True, return_data=True)
        target_part_num = self.config.get("part_number", "")
        if resp:
            val = self._parse_did_string(resp)
            self.log_signal.emit(f"读取结果零件号：{val}", True)
            if target_part_num and target_part_num not in val:
                 self.log_signal.emit(f"警告: 零件号不匹配 (期望: {target_part_num}, 实际: {val})", True)
            elif target_part_num:
                 self.log_signal.emit("零件号匹配校验通过", True)

        # F189 - Software Version (Validate if in config)
        resp = self._send_uds("22 F1 89", "申请读取ECU软件版本号", PHASE_PREP, expect_positive=True, return_data=True)
        target_soft_num = self.config.get("soft_number", "")
        if resp:
            val = self._parse_did_string(resp)
            self.log_signal.emit(f"读取结果ECU软件版本号：{val}", True)
            if target_soft_num and target_soft_num not in val:
                 self.log_signal.emit(f"警告: 软件版本号不匹配 (期望: {target_soft_num}, 实际: {val})", True)
            elif target_soft_num:
                 self.log_signal.emit("软件版本号匹配校验通过", True)

        if not self.running: return

        # 2. Session Control
        if not self._send_uds("10 01", "申请进入默认会话", PHASE_PREP, expect_positive=True, success_msg="进入默认会话请求通过"): return
        if not self._send_uds("10 03", "申请进入扩展会话", PHASE_PREP, expect_positive=True, success_msg="进入扩展会话请求通过"): return

        # 3. Security Access (Level 21/22)
        if not self._perform_security_access(0x21, PHASE_PREP):
             return

        # 4. Check Preconditions (Routine 31 01 21 01)
        resp = self._send_uds("31 01 21 01", "申请检查下载预条件", PHASE_PREP, expect_positive=True, success_msg="检查下载预条件请求通过")
        if not resp: return
        if len(resp) >= 5:
            self.log_signal.emit(f"预条件检查返回状态: 0x{resp[4]:02X}", True)

        # 5. Request File Transfer (Service 38 01 AddFile)
        remote_path = pkg_config.get("filePathAndName", "")

        # Use filename as path if full path not valid or just use what's in config
        if not remote_path:
             remote_path = os.path.basename(self.file_path) # Fallback to filename

        path_bytes = remote_path.encode('ascii')

        # Check filePathAndNameLength from config
        config_path_len_hex = pkg_config.get("filePathAndNameLength", "")
        if config_path_len_hex:
            try:
                # If config specifies length, we might verify or even use it (though actual path bytes drive logic)
                config_path_len = int(config_path_len_hex, 16)
                if config_path_len != len(path_bytes):
                    self.log_signal.emit(f"警告: 配置文件Path长度({config_path_len})与实际({len(path_bytes)})不符", True)
            except:
                pass

        path_len = len(path_bytes)

        # Construct additional parameters from config
        # Default values if missing
        fmt_id = binascii.unhexlify(pkg_config.get("dataFormatIdentifier", "00"))
        fs_len_byte_val = pkg_config.get("fileSizeParameterLength", "04") # Keep as hex string for unhexlify or int? Usually unhexlify.
        fs_len_byte = binascii.unhexlify(fs_len_byte_val)

        fs_uncomp = binascii.unhexlify(pkg_config.get("fileSizeUncompressed", "00000000"))
        fs_comp = binascii.unhexlify(pkg_config.get("fileSizeCompressed", "00000000"))

        # Verify sizes match the fs_len_byte.
        # Ideally we should pad or trim based on fs_len_byte but let's assume config is consistent.

        # 38 01 00 [Len] [Path] [Fmt] [LenSize] [Uncomp] [Comp]
        # Length is 2 bytes for Path Name Length (High Low)
        path_len_high = (path_len >> 8) & 0xFF
        path_len_low = path_len & 0xFF

        req_ft = bytes([0x38, 0x01, path_len_high, path_len_low]) + path_bytes + fmt_id + fs_len_byte + fs_uncomp + fs_comp

        self._send_doip(req_ft, f"申请下载请求 ({remote_path})", expect_positive=True, success_msg="下载请求通过")

        # 6. Transfer Data (Service 36, 1MB blocks)
        # Read max block length from config, default to 1MB (0xF4240)
        block_size_hex = pkg_config.get("maxNumberOfBlockLength", "F4240")
        try:
            block_size = int(block_size_hex, 16)
        except:
            block_size = 1000000

        # Ensure block_size is reasonable (at least 1 byte, max reasonable buffer)
        if block_size < 1: block_size = 1000000

        with open(self.file_path, 'rb') as f:
            block_idx = 1
            while self.running:
                chunk = f.read(block_size)
                if not chunk:
                    break

                # Update hash
                file_hash.update(chunk)

                seq_byte = block_idx & 0xFF
                header = bytes([0x36, seq_byte])
                payload = header + chunk

                desc = f"申请传输数据 Block {block_idx} ({len(chunk)} bytes)"

                # Use robust send with loop for NRC 78
                resp = self._send_doip(payload, desc)
                if not resp or resp[0] != 0x76:
                    self.log_signal.emit(f"传输数据失败: Block {block_idx}", True)
                    return

                percent = int((f.tell() / file_size) * 100)
                self.progress_signal.emit(percent, PHASE_DOWNLOAD, f"传输数据中... {percent}%")

                block_idx += 1

        # 7. Request Transfer Exit (37)
        if not self._send_uds("37", "申请传输结束", PHASE_DOWNLOAD, expect_positive=True, success_msg="传输结束请求通过"): return

        self.progress_signal.emit(0, PHASE_INSTALL, "开始校验与安装...")

        # 8. CheckChecksum (31 01 21 02 + SHA256)
        digest = file_hash.digest() # 32 bytes
        calculated_hash_hex = file_hash.hexdigest()

        # Verify against JSON SHA-256
        config_hash = pkg_config.get("SHA-256", "")
        if config_hash:
            if config_hash.lower() == calculated_hash_hex.lower():
                self.log_signal.emit("本地文件HASH校验通过 (Matches Config)", True)
            else:
                self.log_signal.emit(f"警告: 本地文件HASH与配置不符! \nConfig: {config_hash}\nFile: {calculated_hash_hex}", True)

        routine_check = bytes([0x31, 0x01, 0x21, 0x02]) + digest
        resp = self._send_doip(routine_check, "申请校验文件(SHA256)", expect_positive=True, success_msg="文件校验通过")
        if not resp: return
        # Parse potential status byte from routine result if available (71 01 21 02 [Status])
        if len(resp) >= 5:
            self.log_signal.emit(f"校验返回状态码: 0x{resp[4]:02X}", True)


        # 9. Merge/Erase? (31 01 21 05)
        resp = self._send_uds("31 01 21 05", "申请擦除/合并Memory", PHASE_INSTALL, expect_positive=True, success_msg="Memory操作请求通过")
        if not resp: return
        if len(resp) >= 5:
             self.log_signal.emit(f"Memory操作返回状态: 0x{resp[4]:02X}", True)

        # 10. Re-Authenticate (Session 03 -> SecAccess 21)
        # It seems the device resets session or requires re-auth after 21 05
        if not self._send_uds("10 03", "申请进入扩展会话(Re-Auth)", PHASE_INSTALL, expect_positive=True, success_msg="进入扩展会话请求通过"): return
        if not self._perform_security_access(0x21, PHASE_INSTALL):
             return

        # 11. Install (31 01 21 03 + Date)
        # Date format YYYYMMDD e.g. 20260113 -> 0x20 0x26 0x01 0x13
        now = datetime.datetime.now()
        # Ensure year is 2 bytes context (e.g. 20 26). struct pack >H is big endian short
        # But log shows 20 26 01 13. Year 2026 split as 20, 26.
        # It looks like BCD or just high byte/low byte of year? 2026 hex is 07EA.
        # But log says 20 26. This implies "20" and "26" as decimals representing start of century and year?
        # Or maybe it's literally string bytes? '2026' -> 32 30 32 36. No.
        # Log: 20 26 01 13.
        # 0x20 = 32. 0x26 = 38. This is likely (Century, Year, Month, Day) in BCD-like hex.
        century = int(now.year / 100)
        year_part = now.year % 100
        month = now.month
        day = now.day
        date_payload = bytes([century, year_part, month, day])

        routine_install = bytes([0x31, 0x01, 0x21, 0x03]) + date_payload
        resp = self._send_doip(routine_install, "申请开始安装(2103)", expect_positive=True, success_msg="开始安装请求通过")
        if not resp: return
        if len(resp) >= 5:
            self.log_signal.emit(f"开始安装指令返回状态: 0x{resp[4]:02X}", True)

        # 12. Poll Install State (22 21 04)
        self.log_signal.emit("等待安装完成...", True)

        initial_status_byte = None
        status_changed_no_did = False

        # Installation has no time limit as per user request
        while self.running:

            resp = self._send_uds("22 21 04", "读取安装进度", PHASE_INSTALL, expect_positive=True, return_data=True)
            if resp and len(resp) >= 5:
                # 62 21 04 [Status] [Progress] [Time...]
                # Log: 62 21 04 01 28 ...
                status_byte = resp[3]
                progress = resp[4]

                # Parse additional time info (Bytes 5 to end)
                time_info_str = ""
                if len(resp) > 5:
                    time_bytes = resp[5:]
                    # Attempt to parse time. Assuming it might be HH MM SS or similar BCD/Hex sequence.
                    time_hex = " ".join(f"{b:02X}" for b in time_bytes)

                    # Try to format as Time if count is appropriate (3 bytes = H M S, 2 bytes = M S?)
                    if len(time_bytes) == 4:
                        # Format "Century Year Month Day" e.g. 14 1A 02 02 -> 20 26 02 02 -> 2026.02.02
                        time_info_str = f", 时间: {time_bytes[0]:02d}{time_bytes[1]:02d}.{time_bytes[2]:02d}.{time_bytes[3]:02d}"
                    elif len(time_bytes) == 3:
                        time_info_str = f", 时间: {time_bytes[0]:02d}:{time_bytes[1]:02d}:{time_bytes[2]:02d}"
                    elif len(time_bytes) == 2:
                        time_info_str = f", 时间: {time_bytes[0]:02d}:{time_bytes[1]:02d}"
                    else:
                        time_info_str = f", 时间数据(Hex): {time_hex}"

                # Check DPT for failure status
                warning_msg = ""
                did_found = False

                if self.dpt_manager and self.dpt_manager.dpt_data:
                    # Look for DID 2104
                    did_obj = self.dpt_manager.dpt_data.dids.get("2104")
                    if not did_obj:
                        did_obj = self.dpt_manager.dpt_data.dids.get("0x2104")

                    if did_obj:
                        did_found = True
                        # Assume Status Byte corresponds to the first item (byte "0")
                        status_item = next((item for item in did_obj.items if item.byte == "0"), None)
                        if status_item:
                            conversions = status_item.get_parsed_conversions()
                            # Try to match byte value
                            # Keys could be "2", "0x02", "02" etc.
                            status_key = str(status_byte)
                            status_desc = conversions.get(status_key)
                            if not status_desc:
                                status_desc = conversions.get(f"0x{status_byte:02X}")

                            if status_desc:
                                # Check for failure keywords
                                if "失败" in status_desc or "fail" in status_desc.lower():
                                    self.log_signal.emit(f"检测到安装失败状态: {status_desc} (Code: {status_byte})", True)
                                    self.finished_signal.emit(False, f"安装失败: {status_desc}")
                                    return

                # If DID not found, monitor status change
                if not did_found:
                    if initial_status_byte is None:
                        initial_status_byte = status_byte
                    elif status_byte != initial_status_byte:
                        status_changed_no_did = True

                    if status_changed_no_did:
                         warning_msg = "，未查到对应的DID，已检测到状态变化，请确认是否已经安装失败，失败请手动停止升级流程"

                log_msg = f"安装中... {progress}% (状态: 0x{status_byte:02X}{time_info_str}{warning_msg})"
                self.progress_signal.emit(progress, PHASE_INSTALL, log_msg)

                if progress >= 100:
                    self.log_signal.emit("安装进度达到100%", True)
                    break

            time.sleep(1)

        # 13. Reset
        self._send_uds("11 01", "申请ECU复位", PHASE_INSTALL, success_msg="ECU复位请求通过")

        self.finished_signal.emit(True, "升级完成")

    def _perform_security_access(self, level, phase):
        """Helper for Security Access Sequence"""
        req_seed_hex = f"27 {level:02X}"
        send_key_level = level + 1

        while self.running:
            resp = self._send_uds(req_seed_hex, "申请安全访问种子", phase, expect_positive=True, return_data=True, success_msg="安全访问种子请求通过")
            if not resp:
                self.log_signal.emit("申请安全访问种子失败或无响应，等待1秒后重试...", True)
                time.sleep(1)
                continue

            # Resp: 67 Level Seed...
            # Seed is remaining bytes. Usually 4 bytes?
            # Log: 67 21 C5 74 62 C0 (4 bytes seed: C5 74 62 C0)
            if len(resp) < 3:
                self.log_signal.emit("种子响应长度错误，等待1秒后重试...", True)
                time.sleep(1)
                continue

            seed_bytes = resp[2:]
            self.log_signal.emit(f"读取结果种子：{seed_bytes.hex()}", True)

            # Calculate Key
            key_bytes, err = SecurityAccessHelper.calculate_key(level, seed_bytes)
            if not key_bytes:
                 # Fallback to dummy if DLL fails (for testing/sim) or error
                 self.log_signal.emit(f"计算密钥失败: {err}, 尝试使用全0密钥", True)
                 key_bytes = bytes([0x00] * len(seed_bytes))

            key_str = key_bytes.hex()

            # Send Key (Level + 1)
            key_resp = self._send_uds(f"27 {send_key_level:02X} {key_str}", "申请安全访问密钥验证", phase, expect_positive=True, success_msg="安全访问密钥验证请求通过")
            if key_resp:
                return True
            else:
                self.log_signal.emit("安全访问密钥验证失败，等待1秒后重新申请种子...", True)
                time.sleep(1)
                continue

        return False

    def _parse_did_string(self, resp_bytes):
        if not resp_bytes or len(resp_bytes) < 4:
            return ""
        data = resp_bytes[3:]
        try:
            val = data.decode('ascii', errors='ignore').strip('\x00').strip()
            if not val: return data.hex()
            return val
        except:
            return data.hex()

    def _send_uds(self, hex_str, desc, phase, expect_positive=False, return_data=False, success_msg=None):
        if not self.running: return None
        try:
            payload = binascii.unhexlify(hex_str.replace(" ", ""))
        except:
             if "[KEY]" in hex_str:
                 self.log_signal.emit(f"Error: 尚未计算密钥: {hex_str}", True)
                 return None
             return None
        return self._send_doip(payload, desc, expect_positive=expect_positive, success_msg=success_msg)

    def _send_doip(self, payload, desc, expect_positive=False, success_msg=None):
        # Optimize logging: Only format the part we display to avoid performance hit on large payloads

        # Special handling for Service 36 (TransferData)
        if len(payload) > 0 and payload[0] == 0x36:
             # Just show 36 and Sequence Number
             seq = payload[1] if len(payload) > 1 else 0
             display_hex = f"36 {seq:02X} ..."
        else:
            display_limit = 32
            if len(payload) > display_limit:
                 display_bytes = payload[:display_limit]
                 display_hex = " ".join(f"{b:02X}" for b in display_bytes) + " ..."
            else:
                 display_hex = " ".join(f"{b:02X}" for b in payload)

        # Format: TX   DATA   DESC
        # Align data to 60 chars to ensure description starts at same column
        self.log_signal.emit(f"TX   {display_hex:<60}   {desc}", False)

        try:
            # Send with timeout appropriate for flash operations
            # Use prefer_last=True to handle NRC 78 (Pending) followed by Final Response without manual loop
            # DoIP Client collects responses and prefer_last returns the successful one if Pending preceded it.
            timeout_val = 5.0 # Increased timeout for flash operations
            resp = self.device_service.send_doip_payload(
                payload,
                timeout=timeout_val,
                prefer_last=True
            )

            if isinstance(resp, list):
                 # Should not happen if return_all=False (default), but safety check
                 resp = resp[-1] if resp else None

            if resp:
                # Log RX
                resp_hex = " ".join(f"{b:02X}" for b in resp)
                self.log_signal.emit(f"RX   {resp_hex:<60}", False)

                if resp[0] == 0x7F:
                    nrc = resp[2] if len(resp) > 2 else 00
                    if nrc == 0x78:
                         self.log_signal.emit(f"收到负响应 NRC: 78 (Pending) - 超时未收到最终响应", True)
                         return None # Or handled by loop? But we rely on client loop now.

                    if expect_positive:
                        self.log_signal.emit(f"收到负响应 NRC: {nrc:02X}", True)
                        return None

                elif expect_positive:
                    req_sid = payload[0]
                    resp_sid = resp[0]
                    if resp_sid != (req_sid + 0x40):
                        return None

                    if success_msg:
                        self.log_signal.emit(success_msg, True)

                return resp

            self.log_signal.emit("未收到响应", True)
            return None

        except Exception as e:
            self.log_signal.emit(f"通信错误: {e}", True)
            return None


class UpgradeController(BaseController):
    def __init__(self, parent=None):
        self.model = UpgradeModel(parent)
        self.view = UpgradeView(parent)
        super().__init__(self.model, self.view, parent)

        self.timer = QTimer(self)
        self.stress_current_loop = 0
        self.stress_target_loop = 0
        # Stress test management context
        self.stress_pkg_list = []
        self.stress_pkg_index = 0
        self.stress_total_bytes = 0
        self.stress_completed_bytes = 0

        self.upgrade_steps = []
        self.current_step_index = 0
        self.upgrade_config = {}
        self.is_stress_mode = False
        self.thread = None

        self._setup_connections()

        # Load persisted settings
        self._load_settings()

        # Auto-load files from default update directory if settings were empty
        if not self.view.upgrade_file.text().strip():
             QTimer.singleShot(100, self._auto_load_defaults)

    def _get_config_file_path(self):
        root = os.path.join(get_app_data_path(), "DeviceUpgrade")
        if not os.path.exists(root):
            try:
                os.makedirs(root, exist_ok=True)
            except:
                pass
        return os.path.join(root, "upgrade_config.json")

    def _load_settings(self):
        """Restore previous session paths from JSON config file"""
        try:
            config_file = self._get_config_file_path()
            if not os.path.exists(config_file):
                return

            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Normal Tab
            normal_pkg = data.get("normal_upgrade_file", "")
            normal_cfg = data.get("normal_config_file", "")
            if normal_pkg and os.path.exists(normal_pkg):
                self.view.upgrade_file.setText(normal_pkg)
            if normal_cfg and os.path.exists(normal_cfg):
                self.view.config_file.setText(normal_cfg)

            # Stress Tab
            stress_loop = data.get("stress_loop_count", 100)
            try:
                self.view.stress_loop_spin.setValue(int(stress_loop))
            except:
                pass

            # Restore Stress Tasks
            stress_tasks = data.get("stress_tasks", [])
            if stress_tasks:
                try:
                    self.view.set_stress_task_list(stress_tasks)
                except Exception as e:
                    self._log(f"Error loading stress tasks: {e}", is_info=True)

        except Exception as e:
            self._log(f"Failed to load settings: {e}", is_info=True)

    def _save_settings(self):
        """Persist current paths to JSON config file"""
        try:
            data = {
                "normal_upgrade_file": self.view.upgrade_file.text(),
                "normal_config_file": self.view.config_file.text(),
                "stress_loop_count": self.view.stress_loop_spin.value(),
                "stress_tasks": self.view.get_stress_task_list()
            }

            config_file = self._get_config_file_path()
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

        except Exception as e:
            self._log(f"Failed to save settings: {e}", is_info=True)

    def _auto_load_defaults(self):
        """Try to automatically find and set upgrade files from the update directory (recursive)."""
        try:
            current_dir = os.getcwd()
            update_dir = os.path.join(current_dir, 'app', 'modules', 'device_upgrade', 'update')
            if not os.path.exists(update_dir):
                return

            # Recursive search
            pkg_candidates = []
            cfg_candidates = []

            for root, dirs, files in os.walk(update_dir):
                for f in files:
                    lower_f = f.lower()
                    full_path = os.path.join(root, f)
                    if lower_f.endswith(('.zip', '.bin')):
                        pkg_candidates.append(full_path)
                    elif lower_f.endswith(('.json', '.yaml')):
                        cfg_candidates.append(full_path)

            # Sort by modification time (newest first)
            pkg_candidates.sort(key=os.path.getmtime, reverse=True)
            cfg_candidates.sort(key=os.path.getmtime, reverse=True)

            if pkg_candidates:
                pkg_path = pkg_candidates[0]
                self.view.upgrade_file.setText(pkg_path)
                # Ensure at least one row for stress
                tasks = self.view.get_stress_task_list()
                if not tasks:
                     # View initializes with one row, so this should usually have one empty or partial
                     # But we can force set
                     pass

                # Update first row
                if tasks:
                     tasks[0]['pkg'] = pkg_path
                else:
                     tasks.append({'pkg': pkg_path, 'cfg': ''})

                if cfg_candidates:
                    cfg_path = cfg_candidates[0]
                    self.view.config_file.setText(cfg_path)
                    if tasks:
                        tasks[0]['cfg'] = cfg_path

                self.view.set_stress_task_list(tasks)

        except Exception as e:
            self._log(f"Error auto-loading defaults: {e}", is_info=True)

    def _setup_connections(self):
        # Handle file browsing
        self.view.browse_file_signal.connect(self._handle_browse_request)

        # Text changes to update button states AND save settings
        self.view.upgrade_file.textChanged.connect(self._check_normal_ready)
        self.view.upgrade_file.textChanged.connect(self._save_settings)

        self.view.config_file.textChanged.connect(self._save_settings)
        self.view.stress_loop_spin.valueChanged.connect(self._save_settings)

        self.view.stress_pkg_changed.connect(self._check_stress_ready)
        self.view.stress_pkg_changed.connect(self._save_settings)

        # Normal Upgrade Actions
        self.view.start_btn.clicked.connect(self._start_normal_upgrade)
        self.view.stop_btn.clicked.connect(self._stop_normal_upgrade)

        # Stress Upgrade Actions
        self.view.stress_start_btn.clicked.connect(self._start_stress_upgrade)
        self.view.stress_stop_btn.clicked.connect(self._stop_stress_upgrade)

        # Log Actions
        self.view.clear_btn.clicked.connect(self.view.upgrade_log.clear)

    def _handle_browse_request(self, line_edit, title_filter):
        # Split title and filter if possible or just use title as caption and parse filter
        # title_filter example: "选择升级包 (*.zip *.bin)"
        # We can extract filter if it follows "Title (Filter)" pattern, or just pass it as filter.
        # Simple heuristic: Use full string as caption, and defaults for filter if not easy to split
        # Better: Expected format in view was "Title (*.ext)". QFileDialog takes (parent, caption, dir, filter)

        caption = title_filter
        filter_str = "All Files (*.*)"
        if "(" in title_filter and ")" in title_filter:
            parts = title_filter.rsplit("(", 1)
            caption = parts[0].strip()
            filter_str = title_filter # Use the full string as filter sometimes works or standard format "Name (*.ext)"

        # Set default directory to app/modules/device_upgrade/update
        current_dir = os.getcwd()
        default_dir = os.path.join(current_dir, 'app', 'modules', 'device_upgrade', 'update')
        if not os.path.exists(default_dir):
            default_dir = current_dir # Fallback to current dir if specific folder missing

        file_path, _ = QFileDialog.getOpenFileName(self.view, caption, default_dir, filter_str)
        if file_path:
            line_edit.setText(file_path)

    def _check_normal_ready(self):
        # Enable start if upgrade file is present
        has_file = bool(self.view.upgrade_file.text().strip())
        self.view.start_btn.setEnabled(has_file)

    def _check_stress_ready(self):
        # Start enabled if at least one task is configured
        tasks = self.view.get_stress_task_list()
        has_file = False
        if tasks:
            has_file = bool(tasks[0]['pkg'].strip())
        self.view.stress_start_btn.setEnabled(has_file)

    def _start_normal_upgrade(self):
        self._log("开始常规升级...", is_info=True)
        self.is_stress_mode = False
        if not self._prepare_upgrade():
            return

        # Check DoIP Connection
        device_service: DeviceService = di_container.resolve(DeviceService)
        doip_handler = device_service.get_doip_client()

        if not doip_handler or not doip_handler.connected:
            self._log("错误: DoIP未连接，无法升级", is_info=True)
            QMessageBox.critical(self.view, "Error", "DoIP未连接，无法升级!")
            return

        # Explicitly use the file from the configuration
        file_path = self._find_upgrade_package()
        if not file_path:
             # Fallback to UI or fail
             file_path = self.view.upgrade_file.text().strip()

        if not file_path or not os.path.exists(file_path):
             self._log(f"未找到升级包: {file_path}", is_info=True)
             return

        # Sync UI
        if file_path != self.view.upgrade_file.text().strip():
             self.view.upgrade_file.setText(file_path)

        self.view.start_btn.setEnabled(False)
        self.view.stop_btn.setEnabled(True)
        self.view.normal_progress.setValue(0)

        # Start Worker
        self.thread = UpgradeWorker(self.upgrade_config, file_path, device_service)
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(self._on_worker_progress)
        self.thread.finished_signal.connect(self._on_worker_finished)
        self.thread.start()

    def _prepare_upgrade(self):
        """Preparation for normal upgrade."""
        # Load config to generate steps
        config_path = self.view.config_file.text()

        if not config_path or not os.path.exists(config_path):
            self._log("错误: 未找到配置文件", is_info=True)
            QMessageBox.warning(self.view, "Error", "Config file not found")
            return False

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.upgrade_config = json.load(f)
        except Exception as e:
            self._log(f"读取配置文件失败: {e}", is_info=True)
            return False

        return True

    def _find_upgrade_package(self):
        if not self.upgrade_config or "package" not in self.upgrade_config:
            return None

        pkg = self.upgrade_config["package"][0]
        fname = pkg.get("upgradefile", "")
        if not fname:
            fname = pkg.get("filePathAndName", "")

        if not fname: return None

        # Resolve relative to config file directory
        config_path = self.view.config_file.text()

        # If absolute, verify. If not exists, try relative to config dir.
        if os.path.isabs(fname) and os.path.exists(fname):
            return fname

        # Try relative to config file dir
        config_dir = os.path.dirname(config_path) if config_path else os.getcwd()

        # Optimization: if name is just filename, join with config dir
        # If it's relative path (e.g. "../bin/file.bin"), join works too
        full_path = os.path.join(config_dir, fname)
        if os.path.exists(full_path):
            return full_path

        # Fallback: if fname was absolute but not found, try basename relative to config
        # (Scenario: config moved to another PC)
        if os.path.isabs(fname):
            short_name = os.path.basename(fname)
            full_path_fallback = os.path.join(config_dir, short_name)
            if os.path.exists(full_path_fallback):
                return full_path_fallback

        self._log(f"未找到升级包: {fname} (在 {config_dir} 附近查找)", is_info=True)
        return None

    def _on_worker_progress(self, percent, phase, msg):
        # Logic to update two-stage progress bar
        if self.is_stress_mode:
            try:
                total_tasks = self.stress_target_loop * len(self.stress_task_list)
                if total_tasks > 0:
                    # 获取当前正在执行的任务索引 (在 _run_next_stress_step 中已经 +1，所以这里要 -1)
                    current_idx = self.stress_pkg_index - 1
                    # 已经完全跑完的任务总数
                    completed_tasks = (self.stress_current_loop * len(self.stress_task_list)) + current_idx
                    # 当前任务所占比例加上已完成的任务比例
                    total_percent = int(((completed_tasks + (percent / 100.0)) / total_tasks) * 100)
                    self.view.stress_progress.setValue(min(total_percent, 100))
            except:
                pass
        else:
             self.view.normal_progress.setValue(percent)

        if msg:
            self._log(msg, is_info=True)

    def _on_worker_finished(self, success, msg):
        self._log(f"升级结束: {msg}", is_info=True)

        if self.is_stress_mode:
             # Handle Loop
             if success:

                 # Proceed to next package or next loop
                 self._log("升级完成，准备自动进入下一轮...", is_info=True)
                 QTimer.singleShot(2000, self._run_next_stress_step) # 2s delay
             else:
                 self._stop_stress_upgrade() # Error stops stress
        else:
            self.view.start_btn.setEnabled(True)
            self.view.stop_btn.setEnabled(False)

    def _stop_normal_upgrade(self):
        if self.thread and self.thread.running:
            self.thread.stop()
            self.thread.wait()

        self._log("升级已停止 (用户终止)", is_info=True)
        self.view.start_btn.setEnabled(True)
        self.view.stop_btn.setEnabled(False)
        self.view.normal_progress.setValue(0)

    # Stress mode updates similarly to use thread...
    def _start_stress_upgrade(self):
        self.is_stress_mode = True
        self._log(f"Start Stress Upgrade Loop", is_info=True)

        # Check DoIP
        device_service: DeviceService = di_container.resolve(DeviceService)
        doip_handler = device_service.get_doip_client()
        if not doip_handler or not doip_handler.connected:
             self._log("错误: DoIP未连接", is_info=True)
             return

        # Collect Task List (Pkg + Config)
        self.stress_task_list = []
        has_errors = False

        ui_tasks = self.view.get_stress_task_list()

        for idx, task in enumerate(ui_tasks):
            # task: {'pkg': ..., 'cfg': ...}
            pkg_path = task['pkg'].strip()
            cfg_path = task['cfg'].strip()

            if not pkg_path or not os.path.exists(pkg_path):
                self._log(f"错误: 第 {idx+1} 行未指定有效的升级包", is_info=True)
                has_errors = True

            if not cfg_path or not os.path.exists(cfg_path):
                self._log(f"错误: 第 {idx+1} 行未指定有效的配置文件", is_info=True)
                has_errors = True

            if not has_errors:
                self.stress_task_list.append({'pkg': pkg_path, 'cfg': cfg_path})

        if has_errors or not self.stress_task_list:
             self._log("错误: 升级任务配置有误，无法开始", is_info=True)
             self.is_stress_mode = False
             return

        # Initialize Stress Context
        self.stress_target_loop = self.view.stress_loop_spin.value()
        self.stress_current_loop = 0
        self.stress_pkg_index = 0

        # Calculate Total Size
        total_size_per_loop = sum(os.path.getsize(t['pkg']) for t in self.stress_task_list)
        self.stress_total_bytes = total_size_per_loop * self.stress_target_loop
        self.stress_completed_bytes = 0 # Approximate

        self._log(f"压测任务: {len(self.stress_task_list)} 个任务组合, {self.stress_target_loop} 轮循环, 总大小: {self.stress_total_bytes/1024/1024:.2f} MB", is_info=True)

        self.view.stress_start_btn.setEnabled(False)
        self.view.stress_stop_btn.setEnabled(True)
        self.view.stress_progress.setValue(0)

        # Start First Step
        self._run_next_stress_step()

    def _run_next_stress_step(self):
        """Execute next package in the list, or loop."""
        if not self.is_stress_mode: return

        # Check if we finished all tasks in current loop
        if self.stress_pkg_index >= len(self.stress_task_list):
            self.stress_current_loop += 1
            self.stress_pkg_index = 0
            self._log(f"=== 完成第 {self.stress_current_loop} 轮循环 ===", is_info=True)

        # Check if we finished all loops
        if self.stress_current_loop >= self.stress_target_loop:
             self._log("所有压测循环已完成!", is_info=True)
             self.view.stress_start_btn.setEnabled(True)
             self.view.stress_stop_btn.setEnabled(False)
             self.is_stress_mode = False
             return

        # Prepare Next Task
        current_task = self.stress_task_list[self.stress_pkg_index]
        pkg_path = current_task['pkg']
        cfg_path = current_task['cfg']

        self._log(f"正在执行: Loop {self.stress_current_loop + 1}/{self.stress_target_loop} - Task {self.stress_pkg_index + 1}/{len(self.stress_task_list)}", is_info=True)
        self._log(f"  Pkg: {os.path.basename(pkg_path)}", is_info=True)
        self._log(f"  Cfg: {os.path.basename(cfg_path)}", is_info=True)

        # Advance index for next time
        self.stress_pkg_index += 1

        # Check DoIP again (in case dropped)
        device_service: DeviceService = di_container.resolve(DeviceService)
        doip_handler = device_service.get_doip_client()
        if not doip_handler or not doip_handler.connected:
             # Try reconnect? Rely on Service auto-reconnect or fail?
             if not doip_handler or not doip_handler.connected:
                 self._log("错误: DoIP断开，停止压测", is_info=True)
                 self._stop_stress_upgrade()
                 return

        # Load config for this step
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                self.upgrade_config = json.load(f)
        except Exception as e:
            self._log(f"加载任务配置失败: {e}", is_info=True)
            self._stop_stress_upgrade()
            return

        # Start Worker
        if self.thread and self.thread.isRunning():
            self.thread.wait() # Ensure clean

        self.thread = UpgradeWorker(self.upgrade_config, pkg_path, device_service)
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(self._on_worker_progress)
        self.thread.finished_signal.connect(self._on_worker_finished)
        self.thread.start()

    def _stop_stress_upgrade(self):
        if self.thread and self.thread.running:
            self.thread.stop()
            self.thread.wait()

        self._log("Stress Upgrade Stopped (User Terminated)", is_info=True)
        self.view.stress_start_btn.setEnabled(True)
        self.view.stress_stop_btn.setEnabled(False)
        self.view.stress_progress.setValue(0)

    def _handle_stress_loop_complete(self):
         # Deprecated/Integrated into _run_next_stress_step
         pass

    def _log(self, message, is_info=True):
        """Unified logging helper."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        log_entry = ""
        if is_info:
            log_entry = f"{timestamp}   INFO     {message}"
        else:
            log_entry = f"{timestamp}   {message}"

        if hasattr(self.view, "upgrade_log"):
            self.view.upgrade_log.append(log_entry)

        OperationLogManager.instance().append_log("设备升级", log_entry)

    def append_log(self, message: str):
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")[:-3] + "]"
        log_entry = f"{timestamp} {message}"

        if hasattr(self.view, "upgrade_log"):
            self.view.upgrade_log.append(log_entry)

        OperationLogManager.instance().append_log("设备升级", log_entry)

    def select_all_nodes(self, state: bool):
        """Select or deselect all nodes in the tree."""
        # Assuming the root node is at index 0
        root_index = self.view.model.index(0, 0)
        if not root_index.isValid():
            return

        # Recursively set the check state
        def _set_check_state(index, state):
            if not index.isValid():
                return

            # Set the check state of the current item
            item = self.view.model.itemFromIndex(index)
            if item:
                item.setCheckState(0, state)
                item.setData(state, 32) # Custom role for stress task enabled/disabled

            # Recursively set the check state for children
            if item and item.hasChildren():
                for row in range(item.rowCount()):
                    child_index = item.child(row).index()
                    _set_check_state(child_index, state)

        # Get the current check state of the root node
        root_item = self.view.model.itemFromIndex(root_index)
        if root_item:
            current_state = root_item.checkState(0)

            # Toggle the state
            new_state = not current_state if state is None else state

            # Set the new state
            _set_check_state(root_index, new_state)
