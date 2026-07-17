import os
import datetime
import json
import binascii
import time
import hashlib
import threading
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
    log_signal = pyqtSignal(str, bool)      # Message, IsInfo
    progress_signal = pyqtSignal(int, str, str)  # 0-100%, Phase, LogMsg
    finished_signal = pyqtSignal(bool, str) # success, message

    def __init__(self, config, file_path, device_service):
        super().__init__()
        self.config = config
        self.file_path = file_path
        self.device_service = device_service
        self.running = True
        self.dpt_manager = None
        self._tp_thread = None
        self._last_uds_time = time.time()  # 初始化为当前时间，避免启动后立即发送 3E
        self._tester_present_enabled = self._is_tester_present_enabled()
        self._tester_present_payload = self._get_tester_present_payload()
        # 基于 S3 定时器动态计算 3E 时间参数（符合 ISO 14229-1 标准）
        self._tester_present_interval, self._tester_present_min_idle = self._init_tester_present_timing()
        # 升级阶段管理：控制 3E 在不同阶段的行为
        self._upgrade_phase = "idle"              # idle / pre-programming / download / install / post-install
        self._block_tester_present = False        # 为 True 时后台 3E 线程跳过发送
        self._polls_since_last_tp = 0             # 安装轮询期间内联 3E 计数器
        self._protocol_reconnect_thread = None    # DoIP -> SSH -> SomeIP 顺序恢复线程

    def _is_tester_present_enabled(self):
        """Whether to send automatic TesterPresent during upgrade.

        Default is deliberately False: the upgrade sequence already sends UDS
        traffic continuously during download/install. Injecting 3E from a
        background thread can disturb TransferData / long routine responses.
        """
        values = [
            self.config.get("enable_tester_present"),
            self.config.get("tester_present_enabled"),
            self.config.get("auto_tester_present"),
        ]
        try:
            if "package" in self.config and self.config["package"]:
                pkg = self.config["package"][0]
                values.extend([
                    pkg.get("enable_tester_present"),
                    pkg.get("tester_present_enabled"),
                    pkg.get("auto_tester_present"),
                ])
        except Exception:
            pass

        for val in values:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}
        return False

    def _get_tester_present_payload(self):
        """Get configured TesterPresent payload; prefer 3E 00 over 3E 80 when enabled.

        3E 00 has a real positive response (7E 00), which is safer for socket
        draining than 3E 80. 3E 80 remains configurable for ECUs that require it.
        """
        payload_hex = self.config.get("tester_present_payload", "")
        try:
            if not payload_hex and "package" in self.config and self.config["package"]:
                payload_hex = self.config["package"][0].get("tester_present_payload", "")
        except Exception:
            payload_hex = ""

        payload_hex = (payload_hex or "3E 00").replace(" ", "")
        try:
            payload = binascii.unhexlify(payload_hex)
            if len(payload) >= 2 and payload[0] == 0x3E:
                return payload
        except Exception:
            pass
        return bytes([0x3E, 0x00])

    def _init_tester_present_timing(self):
        """基于 S3 定时器动态计算 TesterPresent 时间参数。

        符合 ISO 14229-1 UDS 标准：
        - S3 Client Timer: ECU 在最后一次收到诊断报文后，等待 S3 时间无新报文则回退到默认会话
        - TesterPresent (3E) 必须在 S3 超时前送达 ECU
        - 行业惯例：3E 发送周期 ≤ S3/2

        计算公式：
        - interval = S3 / 4  （循环检查频率，确保及时捕捉空闲窗口）
        - min_idle = S3 / 2  （最小空闲阈值，确保在 S3/2 时即可发送 3E）
        - 最坏情况：上次 UDS 后 interval + min_idle = 3S3/4 < S3 （保证会话不超时）
        """
        s3_client_s = 3.0  # 默认 3 秒
        try:
            s3_ms = int(self.device_service._config_service.diag_layer_settings.get("s3_client_time", 3000))
            s3_client_s = s3_ms / 1000.0
            if s3_client_s <= 0:
                s3_client_s = 3.0
        except Exception:
            pass

        interval = max(0.5, round(s3_client_s / 4.0, 2))    # S3/4：频繁检查
        min_idle = max(0.5, round(s3_client_s / 2.0, 2))    # S3/2：半周期空闲即发 3E

        self.log_signal.emit(
            f"[3E时间参数] S3={s3_client_s:.1f}s → "
            f"interval={interval:.2f}s, min_idle={min_idle:.2f}s "
            f"(最坏情况 3E 延迟={interval + min_idle:.2f}s < S3={s3_client_s:.1f}s)", True
        )
        return interval, min_idle

    def _send_tester_present_if_safe(self, reason="空闲会话保持"):
        """在UDS空闲窗口发送TesterPresent心跳。

        互斥由 DeviceService._doip_send_lock 统一保证：
        升级期间外部模块已被屏障拦截，此处只需与 Worker 自身的 UDS 串行。
        _last_uds_time 防止在连续 UDS 序列中插入 3E。
        """
        if not self.running or not self._tester_present_enabled:
            return False

        # 阶段拦截：下载和长例程期间禁止后台 3E，防止打断连续传输或抢占 Pending 响应
        if self._block_tester_present:
            return False

        now = time.time()
        if now - self._last_uds_time < self._tester_present_min_idle:
            return False

        doip_client = self.device_service.get_doip_client()
        if not doip_client or not getattr(doip_client, "connected", False):
            self.log_signal.emit("跳过TesterPresent(3E)：DoIP未连接", True)
            return False

        payload = self._tester_present_payload
        display_hex = " ".join(f"{b:02X}" for b in payload)
        suppress_positive = len(payload) > 1 and bool(payload[1] & 0x80)
        timeout_val = 0.5 if suppress_positive else 1.0

        self.log_signal.emit(f"TX   {display_hex:<60}   发送TesterPresent(受控空闲心跳: {reason})", False)
        self._last_uds_time = time.time()
        resp = self.device_service._send_doip_payload_for_upgrade(
            payload,
            timeout=timeout_val,
            prefer_last=True
        )

        if isinstance(resp, list):
            resp = resp[-1] if resp else None

        if isinstance(resp, (bytes, bytearray)) and resp:
            resp_hex = " ".join(f"{b:02X}" for b in bytes(resp))
            self.log_signal.emit(f"RX   {resp_hex:<60}", False)
        # 3E 80 抑制正响应模式无回复，不打印 No Response
        # 3E 00 正常模式无回复也不打印（心跳报文，不报错）

        return True

    def _tester_present_loop(self):
        self.log_signal.emit("TesterPresent(3E)心跳线程已启动：基于升级阶段智能管控，下载/长例程期间自动屏蔽，空闲窗口受控发送", True)
        while self.running:
            for _ in range(int(self._tester_present_interval * 10)):
                if not self.running:
                    break
                time.sleep(0.1)
            self._send_tester_present_if_safe()

    def run(self):
        if self._tester_present_enabled:
            self._tp_thread = threading.Thread(target=self._tester_present_loop, daemon=True)
            self._tp_thread.start()
        else:
            self.log_signal.emit("设备升级自动TesterPresent(3E)已禁用：升级流程中不插入3E，依赖连续UDS报文保持会话", True)
        try:
            self._execute_upgrade()
        except Exception as e:
            self.log_signal.emit(f"升级流程异常: {str(e)}", True)
            self.finished_signal.emit(False, str(e))
        finally:
            self.running = False

    def stop(self):
        self.running = False

    def _check_doip_session_health(self):
        """DoIP 协议级会话健康探测（确定性判断）。

        通过 request_entity_status() 探测 DoIP 会话是否仍然有效：
        - 成功 → 路由激活有效，会话正常
        - 失败 → 路由激活已失效（如控制器重启），需触发完整重连
        """
        try:
            handler = self.device_service._doip_handler
            if not handler or not handler.doip_client:
                return False
            handler.doip_client.request_entity_status()
            return True
        except Exception:
            return False

    def _start_protocol_reconnect(self, device, need_ssh, need_someip):
        """在独立线程中按 DoIP、SSH、SomeIP 顺序恢复原本在线的协议。

        SSH 的服务激活依赖 DoIP，因此即使当前 ECU 探测已经成功，恢复线程
        仍然把 DoIP 作为第一阶段；恢复过程不会阻塞升级线程。每个协议只在
        自身成功后才进入下一阶段，失败则在后台按固定间隔重试。
        """
        if not (need_ssh or need_someip) or not self.running:
            return

        if (self._protocol_reconnect_thread and
                self._protocol_reconnect_thread.is_alive()):
            self.log_signal.emit("协议恢复线程已在运行，跳过重复启动", True)
            return

        def is_connected(status):
            return "成功" in status or "在线" in status

        def protocol_log(message, *unused_args):
            """将 DeviceService 的单参数日志适配到 Worker 的双参数信号。"""
            self.log_signal.emit(str(message), True)

        def ssh_ready(device):
            if not is_connected(str(device.get("ssh_connect_status", ""))):
                return False
            client = self.device_service.get_ssh_client()
            if client is None:
                return False
            is_client_connected = getattr(client, "is_connected", None)
            return bool(is_client_connected()) if callable(is_client_connected) else False

        def someip_ready(device):
            if not is_connected(str(device.get("someip_connect_status", ""))):
                return False
            client = self.device_service.get_someip_client()
            return bool(client and getattr(client, "running", False))

        def wait_interruptible(seconds):
            end_time = time.time() + seconds
            while self.running and time.time() < end_time:
                time.sleep(min(0.2, end_time - time.time()))
            return self.running

        def reconnect_protocols_in_order():
            try:
                # 阶段 1：DoIP。已连接时不额外发送报文；断开时通过升级发送入口
                # 触发 DeviceService 的自动重连和路由激活。
                doip_ready = False
                while self.running and not doip_ready:
                    doip_client = self.device_service.get_doip_client()
                    if doip_client and getattr(doip_client, "connected", False):
                        doip_ready = True
                        break

                    self.log_signal.emit("正在尝试恢复 DoIP 连接...", True)
                    resp = self._send_doip(
                        bytes([0x10, 0x01]),
                        "协议恢复：触发 DoIP 重连",
                        expect_positive=True,
                    )
                    doip_client = self.device_service.get_doip_client()
                    doip_ready = bool(
                        resp and doip_client and
                        getattr(doip_client, "connected", False)
                    )
                    if not doip_ready and not wait_interruptible(2):
                        return

                if not self.running:
                    return
                if not doip_ready:
                    self.log_signal.emit("DoIP 未恢复，暂不尝试依赖 DoIP 的其他协议", True)
                    return

                # 阶段 2：SSH。只清理 SSH，避免影响尚未恢复的 SomeIP。
                ssh_done = not need_ssh or ssh_ready(device)
                if need_ssh and hasattr(self.device_service, "_disconnect_ssh"):
                    try:
                        self.device_service._disconnect_ssh(device, force_cleanup=True)
                    except Exception as exc:
                        self.log_signal.emit(f"清理 SSH 残留连接失败，将继续重试: {exc}", True)

                while self.running and not ssh_done:
                    self.log_signal.emit("正在尝试恢复 SSH 连接...", True)
                    if hasattr(self.device_service, "_connect_ssh"):
                        self.device_service._connect_ssh(device, log_signal=protocol_log)
                    ssh_done = ssh_ready(device)
                    if not ssh_done and not wait_interruptible(2):
                        return

                if not self.running:
                    return

                # 阶段 3：SomeIP。SSH 成功（或原本不需要 SSH）后才开始。
                someip_done = not need_someip or someip_ready(device)
                if need_someip and hasattr(self.device_service, "_disconnect_someip"):
                    try:
                        self.device_service._disconnect_someip(device, force_cleanup=True)
                    except Exception as exc:
                        self.log_signal.emit(f"清理 SomeIP 残留连接失败，将继续重试: {exc}", True)

                while self.running and not someip_done:
                    self.log_signal.emit("正在尝试恢复 SomeIP 连接...", True)
                    if hasattr(self.device_service, "_connect_someip"):
                        self.device_service._connect_someip(device, log_signal=protocol_log)
                    someip_done = someip_ready(device)
                    if not someip_done and not wait_interruptible(2):
                        return

                if self.running and (not need_ssh or ssh_ready(device)) and (not need_someip or someip_ready(device)):
                    self.log_signal.emit("DoIP、SSH、SomeIP 协议顺序恢复操作完成", True)
            except Exception as exc:
                self.log_signal.emit(f"协议顺序恢复时发生异常: {exc}", True)

        self._protocol_reconnect_thread = threading.Thread(
            target=reconnect_protocols_in_order,
            name="upgrade-protocol-reconnect",
            daemon=True,
        )
        self._protocol_reconnect_thread.start()

    def _wait_for_ecu_ready(self):
        self.log_signal.emit("正在轮询请求 ECU 默认会话，以触发网络主动重连与诊断就绪检测...", True)
        wait_start = time.time()
        timeout = 60 # 最大等待60秒
        
        while self.running and (time.time() - wait_start) < timeout:
            try:
                # 无论是否显示 connected 都尝试下发，因为 DeviceService 的 send_doip_payload 会捕获断连并触发自动重连机制
                payload = bytes([0x10, 0x01])
                resp = self._send_doip(payload, "试探 ECU 默认会话能否建立(触发重连)")
                if resp and len(resp) > 0:
                     self.log_signal.emit("ECU 诊断服务已全面就绪", True)
                     
                     # 恢复原本已连接的其他协议：独立后台线程按 DoIP -> SSH -> SomeIP 顺序执行
                     device = getattr(self.device_service, "_last_connected_device", None)
                     if device:
                         ssh_status = str(device.get("ssh_connect_status", ""))
                         someip_status = str(device.get("someip_connect_status", ""))
                         need_ssh = "成功" in ssh_status or "在线" in ssh_status
                         need_someip = "成功" in someip_status or "在线" in someip_status
                         if need_ssh or need_someip:
                             self.log_signal.emit(
                                 "准备在后台按 DoIP → SSH → SomeIP 顺序轮询恢复原本在线的协议...",
                                 True,
                             )
                             self._start_protocol_reconnect(device, need_ssh, need_someip)

                     return True
            except:
                pass

            # 等待 2 秒防止发包太快
            for _ in range(20):
                if not self.running: break
                time.sleep(0.1)

        self.log_signal.emit("警告: 自动触发重连与等待就绪超时，尝试强制继续...", True)
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

        # 进入预编程阶段：后台 3E 由 _last_uds_time 机制自然保护（步骤密集，不会误发）
        self._upgrade_phase = "pre-programming"

        # 2. Session Control
        if not self._send_uds("10 01", "申请进入默认会话", PHASE_PREP, expect_positive=True, success_msg="进入默认会话请求通过"): raise Exception("申请进入默认会话失败或无响应")
        if not self._send_uds("10 03", "申请进入扩展会话", PHASE_PREP, expect_positive=True, success_msg="进入扩展会话请求通过"): raise Exception("申请进入扩展会话失败或无响应")

        # 3. Security Access (Level 21/22)
        if not self._perform_security_access(0x21, PHASE_PREP):
             raise Exception("安全访问不通过或无响应")

        # 4. Check Preconditions (Routine 31 01 21 01)
        resp = self._perform_routine_control(
            binascii.unhexlify("31012101"), "申请检查下载预条件")
        if not resp: raise Exception("检查下载预条件失败或被拒绝")

        # === 进入下载阶段：屏蔽后台 3E，防止打断连续块传输 ===
        self._upgrade_phase = "download"
        self._block_tester_present = True
        self.log_signal.emit("[3E管控] 进入下载阶段，屏蔽后台TesterPresent，避免打断TransferData", True)

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

        resp = self._send_doip(req_ft, f"申请下载请求 ({remote_path})", expect_positive=True, success_msg="下载请求通过")
        if not resp: raise Exception("下载请求(Service 38)失败或被拒绝")

        # 6. Transfer Data (Service 36, 1MB blocks)
        # Read max block length from config, default to 1MB (0xF4240)
        block_size_hex = pkg_config.get("maxNumberOfBlockLength", "F4240")
        try:
            block_size = int(block_size_hex, 16)
        except:
            block_size = 1000000

        # Ensure block_size is reasonable (at least 3 bytes for SID + SeqCounter + 1 byte data)
        if block_size < 3: block_size = 1000000

        # UDS Service 36 Request contains:
        # 0x36 (1 byte) + blockSequenceCounter (1 byte) + data
        # Therefore, the maximum data chunk size is block_size - 2
        chunk_size = block_size - 2

        with open(self.file_path, 'rb') as f:
            block_idx = 1
            while self.running:
                chunk = f.read(chunk_size)
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
                    raise Exception(f"传输数据块 {block_idx} 失败或未收到正响应")

                percent = int((f.tell() / file_size) * 100)
                self.progress_signal.emit(percent, PHASE_DOWNLOAD, f"传输数据中... {percent}%")

                block_idx += 1

        # 7. Request Transfer Exit (37)
        if not self._send_uds("37", "申请传输结束", PHASE_DOWNLOAD, expect_positive=True, success_msg="传输结束请求通过"): raise Exception("申请传输结束(Service 37)失败或被拒绝")

        # === 下载完成，进入安装阶段 ===
        self._upgrade_phase = "install"
        self._block_tester_present = False
        self.log_signal.emit("[3E管控] 下载完成，进入安装阶段，恢复后台TesterPresent能力", True)

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

        # 屏蔽 3E：校验例程可能耗时较长，ECU 可能返回 NRC 78 (Pending)
        self._block_tester_present = True
        routine_check = bytes([0x31, 0x01, 0x21, 0x02]) + digest
        resp = self._perform_routine_control(
            routine_check, "申请校验文件(SHA256)")
        if not resp: raise Exception("文件校验(Routine 2102)请求失败或被拒绝")
        self._block_tester_present = False


        # 屏蔽 3E：擦除/合并例程可能耗时较长
        self._block_tester_present = True
        # 9. Merge/Erase? (31 01 21 05)
        resp = self._perform_routine_control(
            binascii.unhexlify("31012105"), "申请擦除/合并Memory")
        if not resp: raise Exception("擦除/合并Memory(Routine 2105)失败或被拒绝")
        self._block_tester_present = False

        # 10. Re-Authenticate (Session 03 -> SecAccess 21)
        # It seems the device resets session or requires re-auth after 21 05
        if not self._send_uds("10 03", "申请进入扩展会话(Re-Auth)", PHASE_INSTALL, expect_positive=True, success_msg="进入扩展会话请求通过"): raise Exception("重认证: 申请进入扩展会话失败")
        if not self._perform_security_access(0x21, PHASE_INSTALL):
             raise Exception("重认证: 安全访问不通过")

        # 11. Install (31 01 21 03 + Date)
        # Date format YYYYMMDD e.g. 20260113 -> 0x20 0x26 0x01 0x13
        now = datetime.datetime.now()

        def to_bcd(val):
            return (val // 10) * 16 + (val % 10)

        century = to_bcd(now.year // 100)
        year_part = to_bcd(now.year % 100)
        month = to_bcd(now.month)
        day = to_bcd(now.day)
        date_payload = bytes([century, year_part, month, day])

        # 屏蔽 3E：安装例程可能耗时较长
        self._block_tester_present = True
        routine_install = bytes([0x31, 0x01, 0x21, 0x03]) + date_payload
        resp = self._perform_routine_control(
            routine_install, "申请开始安装(2103)")
        if not resp: raise Exception("开始安装指令(Routine 2103)失败或被拒绝")
        self._block_tester_present = False

        # 12. Poll Install State (22 21 04)
        self.log_signal.emit("等待安装完成...", True)
        # 安装轮询阶段：允许后台 3E 在轮询间隙保持会话，并启用内联 3E 作为双重保障
        self._upgrade_phase = "install-polling"
        self._block_tester_present = False
        self._polls_since_last_tp = 0
        self.log_signal.emit("[3E管控] 进入安装轮询阶段，后台3E已恢复，内联3E心跳已激活", True)

        initial_status_byte = None
        status_changed_no_did = False

        # Installation has no time limit as per user request
        while self.running:
            # 内联 TesterPresent 心跳：每 5 次轮询在请求前发送一次 3E，防止 ECU 会话超时
            if self._tester_present_enabled:
                self._polls_since_last_tp += 1
                if self._polls_since_last_tp >= 5:
                    self._send_tester_present_inline("安装轮询会话保持")
                    self._polls_since_last_tp = 0

            resp = self._send_uds("22 21 04", "读取安装进度", PHASE_INSTALL, expect_positive=True, return_data=True, timeout=5.0)
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

            else:
                # UDS 无响应，通过 DoIP 协议级探测确定性判断连接状态
                if self._check_doip_session_health():
                    self.log_signal.emit("DoIP会话健康探测通过，ECU正忙于安装操作，继续轮询", True)
                else:
                    # 确定性判定：DoIP路由激活已失效（如设备重启），触发重连
                    self.log_signal.emit("DoIP会话健康探测失败，路由激活已失效，主动断开并触发重连", True)
                    try:
                        handler = self.device_service._doip_handler
                        if handler:
                            handler.disconnect(source="install_polling_session_dead", reason="entity_status_check_failed")
                            self.device_service._doip_handler = None
                    except Exception:
                        pass
                    # 等待 ECU 就绪（内部自动触发完整重连含路由激活），不断重试直至成功
                    self._wait_for_ecu_ready()

            time.sleep(1)

        # === 轮询结束，屏蔽 3E，准备 ECU 复位 ===
        self._block_tester_present = True
        self._upgrade_phase = "post-install"
        self.log_signal.emit("[3E管控] 安装完成，屏蔽TesterPresent，准备ECU复位", True)

        # 13. Reset
        self._send_uds("11 01", "申请ECU复位", PHASE_INSTALL, success_msg="ECU复位请求通过")

        # 最终清理
        self._upgrade_phase = "idle"
        self._block_tester_present = False

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

    def _perform_routine_control(self, payload, desc, retry_interval=1.0):
        """带无限重试机制的 RoutineControl (Service 31) 发送。

        与 _perform_security_access (Service 27) 保持一致的重试策略：
        while self.running 无限循环重试，直到成功或用户主动停止。

        Args:
            payload: UDS 请求的完整字节数据（包含 SID 31）
            desc: 请求描述，用于日志
            retry_interval: 重试间隔秒数，默认 1.0 秒

        Returns:
            成功返回响应 bytes，用户停止时返回 None
        """
        attempt = 0
        while self.running:
            attempt += 1
            resp = self._send_doip(payload, desc, expect_positive=True)
            if resp:
                if resp[0] == 0x71:
                    if len(resp) >= 5:
                        self.log_signal.emit(f"例程返回状态码: 0x{resp[4]:02X}", True)
                    return resp
                return resp

            self.log_signal.emit(
                f"{desc} 失败或无响应 (第{attempt}次)，"
                f"等待{retry_interval:.0f}秒后重试...", True
            )
            time.sleep(retry_interval)

        return None

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

    def _send_tester_present_inline(self, reason="内联心跳"):
        """在升级流程主线程中同步发送 TesterPresent，仅在安全窗口使用。

        用途：安装轮询阶段，在两次进度查询之间插入 3E，防止 ECU 会话定时器超时。
        与后台线程互斥由 _doip_send_lock 统一保证。
        """
        if not self.running or not self._tester_present_enabled:
            return

        payload = self._tester_present_payload
        display_hex = " ".join(f"{b:02X}" for b in payload)
        suppress_positive = len(payload) > 1 and bool(payload[1] & 0x80)
        timeout_val = 0.5 if suppress_positive else 1.0

        self.log_signal.emit(f"TX   {display_hex:<60}   TesterPresent(内联: {reason})", False)
        self._last_uds_time = time.time()
        try:
            resp = self.device_service._send_doip_payload_for_upgrade(
                payload, timeout=timeout_val, prefer_last=True
            )
            if isinstance(resp, list):
                resp = resp[-1] if resp else None
            if isinstance(resp, (bytes, bytearray)) and resp:
                resp_hex = " ".join(f"{b:02X}" for b in bytes(resp))
                self.log_signal.emit(f"RX   {resp_hex:<60}", False)
        except Exception:
            pass

    def _send_uds(self, hex_str, desc, phase, expect_positive=False, return_data=False, success_msg=None, timeout=None):
        if not self.running: return None
        try:
            payload = binascii.unhexlify(hex_str.replace(" ", ""))
        except:
             if "[KEY]" in hex_str:
                 self.log_signal.emit(f"Error: 尚未计算密钥: {hex_str}", True)
                 return None
             return None
        return self._send_doip(payload, desc, expect_positive=expect_positive, success_msg=success_msg, timeout=timeout)

    def _send_doip(self, payload, desc, expect_positive=False, success_msg=None, timeout=None):
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
            self._last_uds_time = time.time()
            # Send with timeout appropriate for flash operations
            # Use prefer_last=True to handle NRC 78 (Pending) followed by Final Response without manual loop
            # DoIP Client collects responses and prefer_last returns the successful one if Pending preceded it.
            timeout_val = timeout if timeout is not None else 15.0  # 可覆盖；默认15s适用于慢速刷写操作

            resp = self.device_service._send_doip_payload_for_upgrade(
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

                else:
                    # 始终校验响应SID，防止压测轮次间TCP缓冲区残留报文导致响应错位
                    req_sid = payload[0]
                    resp_sid = resp[0]
                    expected_resp_sid = req_sid + 0x40
                    if resp_sid != expected_resp_sid:
                        self.log_signal.emit(
                            f"丢弃报文: 期望响应SID 0x{expected_resp_sid:02X}, "
                            f"实际收到 0x{resp_sid:02X} ", True)
                        return None

                    if expect_positive and success_msg:
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

        # 激活升级屏障：阻止外部3E心跳和其他诊断服务干扰升级
        device_service.begin_upgrade_session()
        self._log("升级屏障已激活：外部3E和其他诊断服务已被屏蔽", is_info=True)

        # Explicitly use the file from the configuration
        file_path = self._find_upgrade_package()
        if not file_path:
             # Fallback to UI or fail
             file_path = self.view.upgrade_file.text().strip()

        if not file_path or not os.path.exists(file_path):
             self._log(f"未找到升级包: {file_path}", is_info=True)
             # 解除升级屏障，避免屏障永久锁死导致所有 DoIP 操作被拦截
             device_service.end_upgrade_session()
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

        # 解除升级屏障（压测模式下每轮结束时解除，下一轮开始时重新激活）
        device_service: DeviceService = di_container.resolve(DeviceService)
        device_service.end_upgrade_session()

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

        # 解除升级屏障
        device_service: DeviceService = di_container.resolve(DeviceService)
        device_service.end_upgrade_session()

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

        # 激活升级屏障：整个压测期间阻止外部诊断干扰
        device_service.begin_upgrade_session()
        self._log("压测升级屏障已激活：外部3E和其他诊断服务已被屏蔽", is_info=True)

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
             # 解除升级屏障
             device_service: DeviceService = di_container.resolve(DeviceService)
             device_service.end_upgrade_session()
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
        # 注意: 压测时这里的 doip_client 可能是断开的(因为上一轮结尾发送了 11 01 ECU复位)，
        # 我们不再因为断开而直接停止压测，而是放行。
        # 后续 UpgradeWorker 启动后的 `_wait_for_ecu_ready` 里面调用 `_send_doip` 时，
        # 底层 DeviceService 的 `send_doip_payload` 会触发自动重连！

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

        # 重新激活升级屏障：_on_worker_finished 在每轮结束时已解除，
        # 下一轮开始前必须重新激活，否则第 2 轮起无屏障保护
        device_service.begin_upgrade_session()

        self.thread = UpgradeWorker(self.upgrade_config, pkg_path, device_service)
        self.thread.log_signal.connect(self._log)
        self.thread.progress_signal.connect(self._on_worker_progress)
        self.thread.finished_signal.connect(self._on_worker_finished)
        self.thread.start()

    def _stop_stress_upgrade(self):
        if self.thread and self.thread.running:
            self.thread.stop()
            self.thread.wait()

        # 解除升级屏障
        device_service: DeviceService = di_container.resolve(DeviceService)
        device_service.end_upgrade_session()

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
