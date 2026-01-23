import json
import os
from datetime import datetime
from PyQt5 import QtCore, QtWidgets
from app.core.base_controller import BaseController
from app.modules.dtc_management.model.dtc_management_model import DTCModel
from app.modules.dtc_management.view.dtc_management_view import DTCView
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.services.diagnostic.dpt_service import DPTService
from app.common.utils.path_utils import get_app_data_path

_dtc_dir = os.path.join(get_app_data_path(), "DTC")
if not os.path.exists(_dtc_dir):
    try:
        os.makedirs(_dtc_dir, exist_ok=True)
    except OSError:
        pass
DTC_LIST_FILE = os.path.join(_dtc_dir, "dtc_list.json")


class DTCController(BaseController):
    dpt_status_signal = QtCore.pyqtSignal(str, str)

    def __init__(self, parent=None):
        self.model = DTCModel(parent)
        self.view = DTCView(parent)
        super().__init__(self.model, self.view, parent)

        self.current_filter = "all"

        # Connect view signals
        self.view.read_dtc_signal.connect(self.handle_read_dtcs)
        self.view.read_freeze_frame_signal.connect(self.handle_read_freeze_frame)
        self.view.filter_changed_signal.connect(self.handle_filter_changed)
        self.view.clear_dtc_signal.connect(self.handle_clear_dtcs)

        # Delay heavy initialization
        QtCore.QTimer.singleShot(0, self.delayed_init)

    def delayed_init(self):
        self._dpt_service = di_container.resolve(DPTService)
        if not self._dpt_service:
             self._dpt_service = DPTService()
             di_container.register_singleton(DPTService, self._dpt_service)

        # Register status callback
        self.dpt_status_signal.connect(self.handle_dpt_status)
        self._dpt_service.add_status_callback(self._on_dpt_status)

        # 加载保存的 DTC 列表
        self.load_dtc_list()
        self.on_model_changed()

    def load_dtc_list(self):
        if not os.path.exists(DTC_LIST_FILE):
             return

        try:
             with open(DTC_LIST_FILE, "r", encoding="utf-8") as f:
                 data = json.load(f)
                 # dtcs stored as list of lists in JSON, convert to list of tuples if needed,
                 # but for now list of lists is compatible if we index it.
                 # Python tuples become lists in JSON.
                 self.model.dtcs = [tuple(x) for x in data.get("dtcs", [])]
                 self.model.freeze_frames = data.get("freeze_frames", [])

                 # Recalculate categories
                 parsed_dtcs = self.model.dtcs
                 total = len(parsed_dtcs)
                 current = sum(1 for x in parsed_dtcs if x[4] == "当前故障")
                 history = sum(1 for x in parsed_dtcs if x[4] == "历史故障")
                 pending = sum(1 for x in parsed_dtcs if x[4] == "未决故障")

                 self.model.categories = [
                    f"全部故障 ({total})",
                    f"当前故障 ({current})",
                    f"历史故障 ({history})",
                    f"未决故障 ({pending})",
                 ]

        except Exception as e:
             self.view.append_log(f"加载 DTC 列表出错: {e}")

    def save_dtc_list(self):
        data = {
            "dtcs": self.model.dtcs,
            "freeze_frames": self.model.freeze_frames
        }
        try:
            with open(DTC_LIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.view.append_log(f"保存 DTC 列表出错: {e}")

    def _on_dpt_status(self, status, message):
        self.dpt_status_signal.emit(status, message)

    def handle_dpt_status(self, status, message):
        self.view.append_log(f"系统: {message}")

    def on_model_changed(self):
        self.refresh_view()
        self.view.populate_freeze_frame(self.model.freeze_frames)

    def get_view(self):
        return self.view

    def handle_filter_changed(self, filter_type):
        self.current_filter = filter_type
        self.refresh_view()

    def refresh_view(self):
        # Filter dtcs
        filtered = []
        if self.current_filter == "all":
            filtered = self.model.dtcs
        elif self.current_filter == "current":
            filtered = [d for d in self.model.dtcs if d[4] == "当前故障"]
        elif self.current_filter == "history":
            filtered = [d for d in self.model.dtcs if d[4] == "历史故障"]
        elif self.current_filter == "pending":
            filtered = [d for d in self.model.dtcs if d[4] == "未决故障"]

        self.view.populate(self.model.categories, filtered)

    def handle_read_dtcs(self):
        if not self._dpt_service.is_ready():
            QtWidgets.QMessageBox.warning(self.view, "提示", "DPT解析未完成，请稍候")
            return

        # Update last read time
        self.view.set_last_read_time(datetime.now())

        device_service = di_container.resolve(DeviceService)
        if not device_service:
             self.view.append_log("未找到设备服务")
             return

        # 19 02 AF
        req_data = bytes([0x19, 0x02, 0xAF])
        self.log_message("TX", req_data)

        # Send request using device_service
        resp = device_service.send_doip_payload(req_data, timeout=2.0)

        if resp:
             self.log_message("RX", resp)
             self.parse_dtc_response(resp)
        else:
             self.view.append_log("无响应")

    def log_message(self, direction, data):
        # Format: YYYY-MM-DD HH:MM:SS.microseconds (6 digits)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        hex_data = " ".join([f"{b:02X}" for b in data])
        self.view.append_log(f"{ts} {direction}: {hex_data}")

    def parse_dtc_response(self, resp):
        try:
            # Response format: 59 02 Mask [DTC1 DTC2 DTC3 Status] ...
            if len(resp) < 3:
                self.view.append_log("响应数据太短")
                return

            if resp[0] != 0x59:
                self.view.append_log(f"负响应或无效 SID: {resp[0]:02X}")
                return

            # availability_mask = resp[2]
            dtc_data = resp[3:]

            parsed_dtcs = []

            # Each DTC is 4 bytes: 3 bytes DTC + 1 byte Status
            num_dtcs = len(dtc_data) // 4

            for i in range(num_dtcs):
                offset = i * 4
                dtc_bytes = dtc_data[offset:offset+3]
                status = dtc_data[offset+3]

                try:
                    dtc_code = self._bytes_to_dtc_code(dtc_bytes)
                except Exception as e:
                    self.view.append_log(f"解析 DTC 字节出错 {dtc_bytes}: {e}")
                    dtc_code = "未知"

                status_hex = f"0x{status:02X}"

                # Determine fault state
                fault_state = self._get_fault_state(status)

                # Get description from DPT service if available
                desc = "未知故障"
                subsystem = "未知"

                try:
                    if self._dpt_service and self._dpt_service.is_ready():
                        dtc_info = self._dpt_service.get_dtc_info(dtc_code)
                        if dtc_info:
                            fetched_desc = dtc_info.get("description")
                            if fetched_desc:
                                desc = str(fetched_desc)
                            # subsystem = dtc_info.get("subsystem", subsystem) # If available
                except Exception as e:
                    self.view.append_log(f"获取 {dtc_code} 信息出错: {e}")

                # Tuple: (code, desc, subsystem, status_code, fault_state, freeze_state)
                # Ensure all elements are strings to prevent UI crashes
                parsed_dtcs.append((
                    str(dtc_code),
                    str(desc),
                    str(subsystem),
                    str(status_hex),
                    str(fault_state),
                    "未读取"
                ))

            # Update model
            self.model.dtcs = parsed_dtcs

            # Update categories counts
            total = len(parsed_dtcs)
            current = sum(1 for x in parsed_dtcs if x[4] == "当前故障")
            history = sum(1 for x in parsed_dtcs if x[4] == "历史故障")
            pending = sum(1 for x in parsed_dtcs if x[4] == "未决故障")

            self.model.categories = [
                f"全部故障 ({total})",
                f"当前故障 ({current})",
                f"历史故障 ({history})",
                f"未决故障 ({pending})",
            ]

            self.model.dataChanged.emit()
            self.view.append_log(f"已解析 {total} 个故障码")
            self.save_dtc_list()

        except Exception as e:
            self.view.append_log(f"解析 DTC 响应出错: {e}")
            import traceback
            traceback.print_exc()

    def _get_fault_state(self, status):
        # Bit 0: testFailed (Current)
        # Bit 3: confirmedDTC (History)
        # Bit 2: pendingDTC (Pending)

        if status & 0x01:
            return "当前故障"
        if status & 0x08:
            return "历史故障"
        if status & 0x04:
            return "未决故障"
        return "历史故障"

    def handle_read_freeze_frame(self, row_index):
        # Get filtered list to find correct DTC
        filtered = self._get_filtered_dtcs()
        if row_index < 0 or row_index >= len(filtered):
            self.view.append_log(f"无效的行索引: {row_index}")
            return

        dtc_entry = filtered[row_index]
        dtc_code = dtc_entry[0] # e.g. "P31AE87"

        self.view.append_log(f"开始读取冻结帧: {dtc_code}")
        self.view.update_freeze_read_status(row_index, False) # Set to reading/failed initially? Or just keep as is.

        # Clear previous freeze frames to show only latest
        self.model.freeze_frames = []
        self.model.dataChanged.emit()

        device_service = di_container.resolve(DeviceService)
        if not device_service:
             self.view.append_log("未找到设备服务")
             return

        # Convert DTC to bytes
        dtc_bytes = self._dtc_code_to_bytes(dtc_code)

        # 19 04 <DTC> FF
        req_data = bytes([0x19, 0x04]) + dtc_bytes + bytes([0xFF])
        self.log_message("TX", req_data)

        resp = device_service.send_doip_payload(req_data, timeout=2.0)

        if resp:
            self.log_message("RX", resp)
            success = self.parse_freeze_frame_response(resp, dtc_code, dtc_entry[1])
            self.view.update_freeze_read_status(row_index, success)

            # Update model persistence
            new_status = "读取成功" if success else "读取失败"
            self._update_dtc_freeze_status(dtc_code, new_status)
        else:
            self.view.append_log("冻结帧无响应")
            self.view.update_freeze_read_status(row_index, False)
            self._update_dtc_freeze_status(dtc_code, "读取失败")

    def _update_dtc_freeze_status(self, code, status):
        # Update the specific DTC in the main model list
        for i, dtc in enumerate(self.model.dtcs):
            if dtc[0] == code:
                # dtc is tuple: (code, desc, subsystem, status_hex, fault_state, freeze_state)
                # or (code, desc, subsystem, status_hex, fault_state)

                # Check tuple length to be safe
                if len(dtc) >= 5:
                    new_dtc = (dtc[0], dtc[1], dtc[2], dtc[3], dtc[4], status)
                    self.model.dtcs[i] = new_dtc
                break
        self.save_dtc_list()

    def handle_clear_dtcs(self):
        device_service = di_container.resolve(DeviceService)
        if not device_service:
             self.view.append_log("未找到设备服务")
             return

        client = device_service.get_doip_client()
        if not client or not client.is_connected():
             self.view.append_log("DoIP 未连接")
             return

        # 14 FF FF FF
        req_data = bytes([0x14, 0xFF, 0xFF, 0xFF])
        self.log_message("TX", req_data)

        # Send request (we might not get response if ECU resets or functional addressing used, but here physical)
        resp = client.send_doip_message(req_data, timeout=2.0)
        if resp:
            self.log_message("RX", resp)

        # Clear model regardless of response (optimistic)
        self.model.dtcs = []
        self.model.freeze_frames = []
        self.model.categories = ["全部故障 (0)", "当前故障 (0)", "历史故障 (0)", "未决故障 (0)"]
        self.model.dataChanged.emit()
        self.view.append_log("已发送清除故障码请求并清空界面")
        self.save_dtc_list()

    def _get_filtered_dtcs(self):
        if self.current_filter == "all":
            return self.model.dtcs
        elif self.current_filter == "current":
            return [d for d in self.model.dtcs if d[4] == "当前故障"]
        elif self.current_filter == "history":
            return [d for d in self.model.dtcs if d[4] == "历史故障"]
        elif self.current_filter == "pending":
            return [d for d in self.model.dtcs if d[4] == "未决故障"]
        return self.model.dtcs

    def _bytes_to_dtc_code(self, b):
        # ISO 15031-6 DTC format
        if len(b) != 3:
            return "000000"

        byte0 = b[0]
        first_nibble = (byte0 & 0xF0) >> 4
        second_nibble = byte0 & 0x0F

        prefix_map = {
            0x0: 'P0', 0x1: 'P1', 0x2: 'P2', 0x3: 'P3',
            0x4: 'C0', 0x5: 'C1', 0x6: 'C2', 0x7: 'C3',
            0x8: 'B0', 0x9: 'B1', 0xA: 'B2', 0xB: 'B3',
            0xC: 'U0', 0xD: 'U1', 0xE: 'U2', 0xF: 'U3',
        }

        prefix = prefix_map.get(first_nibble, '??')
        rest = f"{second_nibble:X}{b[1]:02X}{b[2]:02X}"
        return prefix + rest

    def _dtc_code_to_bytes(self, code: str) -> bytes:
        # P31AE87 -> 31 AE 87 (P=00, but wait)
        # ISO 15031-6:
        # P0 -> 00, P1 -> 01, P2 -> 02, P3 -> 03
        # C0 -> 40, C1 -> 41, C2 -> 42, C3 -> 43
        # B0 -> 80, B1 -> 81, B2 -> 82, B3 -> 83
        # U0=C0, U1=C1, U2=C2, U3=C3

        if len(code) < 7:
            return bytes([0, 0, 0])

        prefix = code[:2]
        rest = code[2:]

        byte0 = 0
        if prefix == 'P0': byte0 = 0x00
        elif prefix == 'P1': byte0 = 0x10 # Wait, P1 is 01? No.
        # First nibble:
        # P=00, C=01, B=10, U=11
        # Second nibble: 0, 1, 2, 3
        # So P0=00, P1=01, P2=02, P3=03
        # C0=40, C1=41, C2=42, C3=43
        # B0=80, B1=81, B2=82, B3=83
        # U0=C0, U1=C1, U2=C2, U3=C3

        # Actually:
        # Bit 7,6: 00=P, 01=C, 10=B, 11=U
        # Bit 5,4: 2nd char of DTC (0,1,2,3)

        map_prefix = {
            'P': 0x00, 'C': 0x40, 'B': 0x80, 'U': 0xC0
        }

        first_char = code[0]
        second_char = code[1]

        val = map_prefix.get(first_char, 0)
        val |= (int(second_char, 16) & 0x3) << 4 # Wait, second char is 0-3 usually?
        # Actually standard says second char is 0,1,2,3.
        # But if it is hex?
        # Let's assume standard DTC format.

        # However, my previous implementation `_bytes_to_dtc_code` did:
        # first_nibble = (byte0 & 0xF0) >> 4
        # prefix_map = {0: 'P0', 1: 'P1', ...}
        # So P0 corresponds to 0x00. P1 to 0x10?
        # Let's check `_bytes_to_dtc_code`:
        # 0x0 -> P0. 0x0 = 0000.
        # 0x1 -> P1. 0x1 = 0001. (High nibble 0001 = 1) -> 0x10
        # So P1xxxx is 0x1x xx xx.

        # So:
        # P0 -> 0x00
        # P1 -> 0x10
        # P2 -> 0x20
        # P3 -> 0x30
        # C0 -> 0x40
        # ...

        base = 0
        if first_char == 'P': base = 0x00
        elif first_char == 'C': base = 0x40
        elif first_char == 'B': base = 0x80
        elif first_char == 'U': base = 0xC0

        second_digit = int(second_char, 16)
        byte0 = base | (second_digit << 4) # Wait, no.
        # If P1, base=0, second=1. 0 | (1<<4) = 0x10. Correct.
        # If U0, base=0xC0, second=0. 0xC0 | 0 = 0xC0. Correct.

        # But wait, the rest of byte0 comes from 3rd char?
        # DTC is 3 bytes.
        # Byte 0: [Type 2bit][2nd char 2bit][3rd char 4bit]
        # Byte 1: [4th char][5th char]
        # Byte 2: [6th char][7th char]

        # Example P31AE87
        # P3 -> 0x3?
        # 1 -> 3rd char.
        # AE -> Byte 1
        # 87 -> Byte 2

        # So Byte 0 = (Type << 6) | (2nd << 4) | 3rd
        # P=00, C=01, B=10, U=11

        type_bits = 0
        if first_char == 'P': type_bits = 0
        elif first_char == 'C': type_bits = 1
        elif first_char == 'B': type_bits = 2
        elif first_char == 'U': type_bits = 3

        byte0 = (type_bits << 6) | (int(second_char, 16) << 4) | int(code[2], 16)
        byte1 = int(code[3:5], 16)
        byte2 = int(code[5:7], 16)

        return bytes([byte0, byte1, byte2])

    def parse_freeze_frame_response(self, resp, dtc_code, dtc_desc):
        # 59 04 [DTC 3] [Status 1] [RecNum 1] [NumID 1] [DID 2] [Data N] ...
        if len(resp) < 6:
            return False
        if resp[0] != 0x59 or resp[1] != 0x04:
            return False

        # Extract info
        # dtc_bytes = resp[2:5]
        status = resp[5] # Status of DTC

        offset = 6
        success = False

        # Determine Fault Type from Status? Or just uses Status byte.
        # User screenshot shows "Type A" in Type column.
        # Usually UDS doesn't provide "Type A" explicitly in 19 04.
        # Maybe it comes from parsed DTC info or just hardcoded for valid snapshot?
        # Let's show Status Hex for now or mapping if we had one.
        type_str = f"Status 0x{status:02X}"

        # Loop over records
        while offset < len(resp):
            if offset + 2 > len(resp):
                break

            rec_num = resp[offset]
            num_ids = resp[offset+1]
            offset += 2

            # For each DID in this record
            for _ in range(num_ids):
                if offset + 2 > len(resp):
                    break

                did_val = (resp[offset] << 8) | resp[offset+1]
                offset += 2
                did_hex = f"{did_val:04X}"

                did_len = 0
                params = []

                # Check DPT
                parser = None
                if self._dpt_service:
                    parser = self._dpt_service.get_parser(did_hex)

                if parser:
                    # Calculate expected length
                    if parser._fields:
                        did_len = max(f.byte_offset + f.byte_length for f in parser._fields)

                    if offset + did_len > len(resp):
                         self.view.append_log(f"DID {did_hex} 数据被截断")
                         break

                    chunk = resp[offset : offset + did_len]
                    offset += did_len

                    # Parse
                    result = parser.parse_bytes(chunk)

                    for f in result.fields:
                         # Split range
                         byte_str = "All"
                         bit_str = "All"
                         if "/" in f.range_str:
                             parts = f.range_str.split("/")
                             byte_str = parts[0]
                             if len(parts) > 1:
                                 bit_str = parts[1]

                         # Separate Value/Unit
                         val_txt = f.parsed_value
                         unit_txt = f.unit

                         if unit_txt and val_txt.endswith(" " + unit_txt):
                             val_txt = val_txt[:-len(unit_txt)-1]
                         elif unit_txt and val_txt.endswith("(" + unit_txt + ")"):
                              val_txt = val_txt[:-len(unit_txt)-2].strip()

                         params.append({
                             "byte": byte_str,
                             "bit": bit_str,
                             "name": f.name if not f.group else f"[{f.group}] {f.name}",
                             "value": val_txt,
                             "unit": unit_txt
                         })
                else:
                    # Unknown DID - Strategy: Stop parsing record?
                    # If we don't know length, we can't continue to next DID.
                    # We consume rest of buffer if it looks like end?
                    # Or just fail this record.
                    self.view.append_log(f"冻结帧中发现未知 DID: {did_hex}。无法继续解析流。")
                    params.append({
                        "byte": "?", "bit": "?",
                        "name": f"DID 0x{did_hex} (未知)",
                        "value": "结构未知",
                        "unit": ""
                    })
                    # Force break outer loop as we are desynchronized
                    offset = len(resp)
                    break

                # Add Entry per DID
                self.model.freeze_frames.append({
                    "code": dtc_code,
                    "desc": dtc_desc,
                    "type": type_str,
                    "did": f"0x{did_hex}",
                    "length": did_len,
                    "params": params
                })
                success = True

        self.model.dataChanged.emit()
        return success
