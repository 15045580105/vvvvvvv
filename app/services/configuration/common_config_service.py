import logging
from typing import List, Dict, Any, Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal

from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService as SystemConfigService
# Use new DPTManager to handle logic
from app.common.utils.dpt_manager import DPTManager
from extract_routine_data import extract_routine_data
import json
import os

logger = logging.getLogger(__name__)

class CommonConfigService(QObject):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._device_service: Optional[DeviceService] = None
        self._system_config_service = SystemConfigService()
        self._config_name = "common_config_settings"


    def inject_device_service(self, device_service: DeviceService):
        self._device_service = device_service


    def read_param(self, did: str) -> Optional[str]:
        """读取参数值"""
        if not self._device_service:
            self.log_signal.emit("设备服务未连接")
            return None

        client = self._device_service.get_doip_client()
        if not client:
            self.log_signal.emit("DoIP客户端未连接")
            return None

        try:
            did_int = int(did, 16)
            did_bytes = did_int.to_bytes(2, 'big')
        except ValueError:
            self.log_signal.emit(f"无效的DID: {did}")
            return None

        # 22 DID
        cmd = bytes([0x22]) + did_bytes
        self.log_signal.emit(f"发送读取指令: {cmd.hex(' ').upper()}")

        resp = client.send_doip_message(cmd)
        if resp and resp[0] == 0x62:
            # 62 DID DATA...
            data = resp[3:]
            # 尝试解码为ASCII，如果失败则显示Hex
            try:
                val_str = data.decode('ascii').strip()
                # 过滤不可见字符
                val_str = ''.join([c for c in val_str if c.isprintable()])
            except:
                val_str = data.hex(' ').upper()

            self.log_signal.emit(f"读取成功: {val_str}")
            return val_str
        else:
            err = resp.hex(' ').upper() if resp else "无响应"
            self.log_signal.emit(f"读取失败: {err}")
            return None


    def execute_routine(self, rid: str) -> bool:
        """执行例程"""
        if not self._device_service:
            self.log_signal.emit("设备服务未连接")
            return False

        try:
            rid_int = int(rid, 16)
            # 这里假设是 31 01 RID
            # 注意：有些例程可能需要参数，这里简化为无参例程
            # 如果是 11 服务 (ECU Reset)，则不是 RID
            if rid == "1101": # 假设这是复位
                cmd = bytes([0x11, 0x01])
            elif rid == "1103":
                cmd = bytes([0x11, 0x03])
            else:
                rid_bytes = rid_int.to_bytes(2, 'big')
                cmd = bytes([0x31, 0x01]) + rid_bytes
        except ValueError:
            self.log_signal.emit(f"无效的RID: {rid}")
            return False

        # 使用 execute_secure_routine 来处理安全访问（如果需要）
        # 这里假设常用例程可能需要安全访问
        self.log_signal.emit(f"发送执行指令: {cmd.hex(' ').upper()}")

        # 注意：execute_secure_routine 返回的是响应bytes或False
        # 这里我们假设 sec_level=0x01 (根据之前的代码)
        # DeviceService 的 execute_secure_routine 已经被要求修改为不接受 log_callback，或者如果它还没被修改，我们需要修改它。
        # 假设 DeviceService 已经或将要被修改为使用信号，或者我们需要传入一个适配器。
        # 鉴于用户要求“全部更改”，DeviceService 也应该改。
        # 这里暂时不传 log_callback，假设 DeviceService 会自己 log 或者我们不需要从它那里通过 callback 获取 log。
        # 但要注意 execute_secure_routine 的定义。如果它强制要求 callback，并在内部调用，那我们得传点东西。
        # 暂时传入 self.log_signal.emit 作为 callback？不，用户说“全部更改为日志通过信号转来发”。
        # 如果 execute_secure_routine 也改成了信号，那这里不需要传。
        resp = self._device_service.execute_secure_routine(cmd, sec_level=0x01, log_signal=self.log_signal)

        if resp:
            # 检查响应
            # 11服务响应是 51
            # 31服务响应是 71
            if cmd[0] == 0x11 and resp[0] == 0x51:
                self.log_signal.emit("执行成功")
                return True
            elif cmd[0] == 0x31 and resp[0] == 0x71:
                self.log_signal.emit("执行成功")
                return True
            else:
                self.log_signal.emit(f"执行失败，响应: {resp.hex(' ').upper()}")
                return False
        else:
            self.log_signal.emit("执行失败")
            return False

    def execute_2e_service(self, service_info):
        """执行 2E 服务"""
        # 使用类内部的信号发射函数作为日志记录器
        _log = self.log_signal.emit

        if not self._device_service:
            _log("设备服务未连接")
            return False

        service_id_hex = service_info.get("serviceId", "").replace("0x", "")
        if not service_id_hex:
            _log("未配置 Service ID")
            return False

        try:
            did_int = int(service_id_hex, 16)
        except ValueError:
            _log(f"无效的 Service ID: {service_id_hex}")
            return False

        param_obj_val = service_info.get("paramObject_val", "")
        param_state_val = service_info.get("paramState_val", "")
        param_obj_conf = service_info.get("paramObject", {})

        byte_val = None
        bypass_dpt = False

        # --- 特殊逻辑: 0x0110 工厂模式 ---
        if did_int == 0x0110:
            # 根据需求，工厂模式与非工厂模式均对应 0xFF
            is_non_factory = "非工厂" in param_state_val or "Default" in param_state_val or "用户" in param_state_val or "User" in param_state_val
            is_factory = "工厂" in param_state_val or "Factory" in param_state_val

            if is_non_factory:
                byte_val = bytes([0x01])
                bypass_dpt = True
            elif is_factory:
                byte_val = bytes([0xFF])
                bypass_dpt = True

        # --- Handle DPT Logic ---
        if not bypass_dpt:
            # 1. 尝试获取 paramObject 中的 placeholder
            # 如果 placeholder 存在，它可能对应 DPT 配置中的 SubDataName (例如 "CMS IP Address")
            placeholder = param_obj_conf.get("placeholder", "") if isinstance(param_obj_conf, dict) else ""

            # 2. 如果 placeholder 存在，使用它作为 key 去查找 DPT，而不是 input value ("192.168.1.22")
            # 这样 input value 就可以被 dpt_manager 按照 ASCII encoding 处理 for "CMS IP Address"

            dpt_lookup_key = ""
            param_value_to_process = "" # This will be the value encoded/calculated

            if placeholder:
                 dpt_lookup_key = placeholder
                 param_value_to_process = param_obj_val # User input from paramObject column
            else:
                 # Default behavior: paramObject_val IS the key (e.g. dropdown selection)
                 dpt_lookup_key = param_obj_val
                 param_value_to_process = param_state_val # User input/selection from paramState column

            # Check paramState config for placeholder too
            param_state_conf = service_info.get("paramState", {})
            placeholder_state = param_state_conf.get("placeholder", "") if isinstance(param_state_conf, dict) else ""

            final_bytes_accumulated = None

            # Handle 2E DPT path check
            dpt_path_valid = (hasattr(self, 'dpt_file_path_2e') and self.dpt_file_path_2e) or \
                             (hasattr(self, 'dpt_file_path') and self.dpt_file_path)

            if dpt_path_valid:
                 # Strategy:
                 # If placeholders exist, assume they are the DPT Item Names.
                 # Process paramObject input -> Item 1
                 # Process paramState input -> Item 2 (if exists)
                 # Then merge results.

                 # --- Process Param Object Input ---
                 key_obj = placeholder if placeholder else param_obj_val
                 val_obj = param_obj_val if placeholder else param_state_val

                 res_1 = self._calculate_byte_from_dpt(
                     service_id_hex,
                     key_obj, # param_obj (Lookup Name)
                     val_obj, # param_state (Value)
                     service_info=service_info,
                 )

                 # --- Process Param State Input ---
                 # If paramState also has a placeholder, it means it maps to ANOTHER item
                 if placeholder_state and param_state_val:
                     res_2 = self._calculate_byte_from_dpt(
                         service_id_hex,
                         placeholder_state, # Lookup Name (e.g. "CMS Port")
                         param_state_val,   # Value (e.g. "5566")
                         service_info=service_info,
                     )

                     # Merge res_1 and res_2
                     # Both returns should be bytes (bytearray-like from dpt_manager)
                     # We need to overlay them.
                     if res_1 and res_2:
                         # Assume same length if from same DID
                         len_max = max(len(res_1), len(res_2))
                         merged = bytearray(len_max)

                         for i in range(len_max):
                             b1 = res_1[i] if i < len(res_1) else 0
                             b2 = res_2[i] if i < len(res_2) else 0
                             merged[i] = b1 | b2 # Bitwise OR works if fields don't overlap

                         byte_val = bytes(merged)
                     elif res_1:
                         byte_val = res_1
                     elif res_2:
                         byte_val = res_2

                 else:
                     byte_val = res_1

        data_bytes = b''

        if byte_val is not None:
             # Calculate Byte Value from DPT now returns bytes (or int, handling both)
             if isinstance(byte_val, (bytes, bytearray)):
                 data_bytes = byte_val
             # else: implicitly ignored as unreachable
             #     pass

        else:
            # Fallback to existing logic
            param_value_source = service_info.get("requestConfig", {}).get("paramValueSource", "raw")

            if param_value_source == "hex":
                # hex 模式通常 paramObject_val 已经是 hex string
                try:
                    cleaned_hex = param_obj_val.replace(" ", "")
                    data_bytes = bytes.fromhex(cleaned_hex)
                except:
                    _log(f"无效的 Hex 数据: {param_obj_val}")
                    return False
            elif param_value_source == "ascii":
                 data_bytes = param_obj_val.encode('ascii')
            elif param_value_source == "calculated":
                 # 简化的计算逻辑：尝试从 paramState_val (如 "ON/OFF", "0x01") 提取数值
                 val_int = 0
                 # Try to extract hex
                 import re
                 hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state_val)
                 if hex_match:
                     val_int = int(hex_match.group(1), 16)
                 else:
                     # Simple mapping
                     if "ON" in param_state_val or "使能" in param_state_val: val_int = 1
                     elif "OFF" in param_state_val or "禁用" in param_state_val: val_int = 0
                     else:
                          # try raw int
                          try:
                              val_int = int(param_state_val)
                          except:
                              pass
                 data_bytes = bytes([val_int])
            # ... 更多类型 ...
            else:
                 # Default logic if config is missing specific source logic
                 # Fallback to similar logic as 'calculated'
                 val_int = 0
                 import re
                 hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state_val)
                 if hex_match:
                     val_int = int(hex_match.group(1), 16)
                 else:
                     if "ON" in param_state_val or "使能" in param_state_val: val_int = 1
                     elif "OFF" in param_state_val or "禁用" in param_state_val: val_int = 0
                     else:
                          try:
                              val_int = int(param_state_val)
                          except:
                              pass
                 data_bytes = bytes([val_int])

        # 构造完整 UDS 指令: 2E + DID(2 bytes) + DATA
        did_bytes = did_int.to_bytes(2, 'big')
        command = bytes([0x2E]) + did_bytes + data_bytes

        _log(f"发送指令: {command.hex(' ').upper()}")

        # 执行 UDS (需要安全访问 27 01)
        resp = self._device_service.execute_secure_routine(command, sec_level=0x01, log_signal=self.log_signal)

        if resp and resp[0] == 0x6E: # Positive Response for 2E is 6E
             _log("执行成功")
             return True
        else:
             _log(f"执行失败: {resp.hex(' ').upper() if resp else '无响应'}")
             return False


    def set_dpt_file_path(self, path, config_type="2E"):
        """设置 DPT 文件路径
        :param config_type:
        """

        self.dpt_file_path = path

    def _calculate_byte_from_dpt(self, did_hex, param_obj_selected, param_state_selected, service_info=None):
        """根据 DPT 文件定义计算 Byte 值"""
        _log = self.log_signal.emit
        # Ensure we use the correct DPT path (Logic from existing code)
        dpt_path = None
        if hasattr(self, 'dpt_file_path_2e') and self.dpt_file_path_2e:
           dpt_path = self.dpt_file_path_2e
        elif hasattr(self, 'dpt_file_path') and self.dpt_file_path:
           dpt_path = self.dpt_file_path

        if not dpt_path:
             _log("DPT 文件路径未设置")
             return None



        # Optimize: Check if we have a cached manager or create new one?
        if not hasattr(self, '_dpt_manager'):
             self._dpt_manager = DPTManager()
             self._dpt_manager.load_dpt_from_file(dpt_path)
             self._current_dpt_path = dpt_path # Track loaded path
        else:
             # Check if path changed
             if getattr(self, '_current_dpt_path', None) != dpt_path:
                  self._dpt_manager.load_dpt_from_file(dpt_path)
                  self._current_dpt_path = dpt_path

        # --- 兼容处理逻辑 ---
        # 如果参数对象为 "/", "", "---" 或空，且参数状态有效，则使用 content 字段 (去掉ID后缀) 作为参数对象进行计算
        local_param_obj = param_obj_selected

        is_obj_invalid = False
        if isinstance(local_param_obj, str):
             if local_param_obj.strip() in ["", "---", "/"]:
                 is_obj_invalid = True
        elif isinstance(local_param_obj, list):
             if not local_param_obj: # empty list
                 is_obj_invalid = True
             elif len(local_param_obj) == 1 and local_param_obj[0] in ["", "---", "/"]:
                 is_obj_invalid = True

        if is_obj_invalid and param_state_selected and (isinstance(param_state_selected, str) and param_state_selected not in ["---", ""]):
             content_raw = (service_info or {}).get("content", "")
             # 提取中文名称，例如 "OBD CAN开关配置(0xBE1B)" -> "OBD CAN开关配置"
             if "(" in content_raw:
                 obj_name = content_raw.split("(")[0].strip()
             else:
                 obj_name = content_raw.strip()

             if obj_name:
                 _log(f"参数对象为空/无效，使用 Content 名称: '{obj_name}' 进行计算")
                 local_param_obj = obj_name
        # --- 结束兼容处理 ---

        # 统一标准化为列表处理：支持单选(str)和多选([str, str])
        objects_to_process = []
        if isinstance(local_param_obj, list):
            objects_to_process = local_param_obj
        else:
            objects_to_process = [local_param_obj]

        final_val = 0
        calculated_any = False
        target_len = 1

        for obj in objects_to_process:
            # 遍历每一个选项，计算其在 byte 中的值
            val = self._dpt_manager.calculate_byte_val(did_hex, obj, param_state_selected, _log)
            if val is not None:
                # 累加值 (使用按位或，因为通常是不同 bit 位)
                val_int = int.from_bytes(val, 'big')
                final_val |= val_int
                target_len = len(val)
                calculated_any = True

        if calculated_any:
             _log(f"DPT计算成功: {final_val:02X}")
             return final_val.to_bytes(target_len, 'big')
        else:
             _log(f"DPT计算失败或未选中有效对象")
             return None

    def load_2e_config(self, file_path: str) -> List[Dict[str, Any]]:
        """加载 2E 配置 JSON 文件"""
        import json
        import os

        if not os.path.exists(file_path):
            logger.error(f"配置文件不存在: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("services", [])
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return []

    def save_last_2e_config_path(self, file_path: str):
        """保存最后一次加载的 2E 配置文件路径"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings is None:
            settings = {}
        settings["last_2e_config_path"] = file_path
        self._system_config_service.save_json(self._config_name, settings)

    def get_last_2e_config_path(self) -> Optional[str]:
        """获取最后一次加载的 2E 配置文件路径"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings:
            return settings.get("last_2e_config_path")
        return None

    def load_routine_config(self, file_path: str) -> List[Dict[str, Any]]:
        """加载 31&2F 配置 JSON 文件"""
        if not os.path.exists(file_path):
            logger.error(f"配置文件不存在: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("services", [])
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return []

    def save_last_routine_config_path(self, file_path: str):
        """保存最后一次加载的 31&2F 配置文件路径"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings is None:
            settings = {}
        settings["last_routine_config_path"] = file_path
        self._system_config_service.save_json(self._config_name, settings)

    def get_last_routine_config_path(self) -> Optional[str]:
        """获取最后一次加载的 31&2F 配置文件路径"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings:
            return settings.get("last_routine_config_path")
        return None

    def execute_routine_service(self, service_info: Dict[str, Any]) -> bool:
        """执行 $31 / $2F 服务 (适配 View 闭包调用)"""
        # 兼容旧代码，这里直接调用 execute_routine_v2
        # 注意：View 中传递的 service_info 已经包含了 paramObject_val 和 paramState_val (如果是 CheckableComboBox 动态绑定的)
        # 如果没有值，则默认为 '---'
        
        param_obj_val = service_info.get("paramObject_val", "---")
        param_state_val = service_info.get("paramState_val", "---")
        routine_control_type_val = service_info.get("routineControlType_val", "---")
        
        return self.execute_routine_v2(service_info, param_obj_val, param_state_val, routine_control_type_val)

    def execute_routine_v2(self, service_info: Dict[str, Any], param_obj_val: str, param_state_val: str, routine_control_type_val: str) -> bool:
        """
        执行 $31 / $2F 服务 (New Logic)
        """
        _log = self.log_signal.emit

        if not self._device_service or not self._device_service.get_doip_client():
            _log("设备未连接 (DoIP)，无法执行服务")
            # return False

        service_id = service_info.get("serviceId", "")
        if not service_id:
             _log("配置错误: 缺少 Service ID")
             return False

        did_key = service_id

        # Parse Routine Control Type (SubFunction or IOCP)
        control_type_int = -1
        try:
            if routine_control_type_val and ":" in routine_control_type_val:
                part = routine_control_type_val.split(":")[0].strip()
                control_type_int = int(part, 16)
            elif routine_control_type_val and routine_control_type_val not in ["---", "N/A", "", "/"]:
                val_clean = routine_control_type_val.strip()
                control_type_int = int(val_clean, 16) if "0x" in val_clean.lower() else int(val_clean)
        except Exception:
            # _log(f"解析 Routine Control Type 失败: {routine_control_type_val}")
            pass

        # Check Service Type (2F or 31)
        is_2f_service = False
        try:
            req_service = service_info.get('request', {}).get('service', '')
            if req_service and int(req_service.replace("0x", ""), 16) == 0x2F:
                is_2f_service = True
        except:
            pass

        bypass_dpt = False

        # User N/A check
        na_list = ["N/A", "---", "", "/"]
        is_obj_na = param_obj_val in na_list
        is_state_na = param_state_val in na_list

        if is_obj_na and is_state_na:
            _log("参数对象和状态均为 N/A，不携带数据载荷 (No Data)")
            bypass_dpt = True

        # Special logic for 2F ReturnControl (0x00) -> No Data
        if is_2f_service and control_type_int == 0x00:
             bypass_dpt = True
             _log("2F服务 ControlType=0x00 (ReturnControlToECU)，无需数据载荷")

        final_bytes = b''

        if not bypass_dpt:
            # 1. Load DPT Data (if not loaded)
            dpt_path = None
            if hasattr(self, 'dpt_file_path_routine') and self.dpt_file_path_routine:
               dpt_path = self.dpt_file_path_routine
            elif hasattr(self, 'dpt_file_path_2e') and self.dpt_file_path_2e:
                 dpt_path = self.dpt_file_path_2e
            elif hasattr(self, 'dpt_file_path') and self.dpt_file_path:
               dpt_path = self.dpt_file_path

            if not dpt_path:
                 _log("DPT 文件路径未设置，无法解析 Routine bit 位")
                 return False

            if not hasattr(self, '_dpt_manager'):
                 self._dpt_manager = DPTManager()
                 self._dpt_manager.load_dpt_from_file(dpt_path)
                 self._current_dpt_path = dpt_path
            else:
                 if getattr(self, '_current_dpt_path', None) != dpt_path:
                      self._dpt_manager.load_dpt_from_file(dpt_path)
                      self._current_dpt_path = dpt_path

            # 2. Find DID Item in DPT
            did_key = service_id
            if not did_key.startswith("0x"):
                 if any(k.endswith(did_key) for k in self._dpt_manager.dpt_data.dids.keys()):
                     did_key = "0x" + did_key

            did_obj = self._dpt_manager.dpt_data.dids.get(did_key)
            if not did_obj:
                for k, v in self._dpt_manager.dpt_data.dids.items():
                    if k.lower() == did_key.lower():
                         did_obj = v
                         break

            if not did_obj:
                 _log(f"DPT 中未找到 DID: {did_key}")
                 return False

            # 3. Extract Routine Control Option (Request) from Raw Data
            raw_data = did_obj.raw_data or {}

            # Use strict routine_control_type_val for looking up options
            routine_data = extract_routine_data(raw_data, routine_control_type_val)

            # 4. Get the options array
            if is_2f_service:
                options_array = routine_data.get('ControlOption\n(Request)', [])
            else:
                options_array = routine_data.get('RoutineControlOption\n(Request)', [])

            if not options_array:
                 _log(f"DPT Control Type '{routine_control_type_val}' 下未找到 definitions")
                 # return False # Could just mean no data needed? Let's assume fail for now if user provided params
                 if not is_obj_na:
                     return False

            if options_array:
                # 5. Process Bits based on Param Object & Param State
                max_byte = 0
                for item in options_array:
                     try:
                         byte_val = item.get("byte", 0)
                         if isinstance(byte_val, str) and byte_val.startswith("#"):
                             b = int(byte_val[1:]) - 5
                         else:
                             b = int(byte_val)
                         max_byte = max(max_byte, b)
                     except: pass

                total_len = max_byte + 1
                final_bytes = bytearray(total_len)

                target_items = []
                is_all_explicit = param_obj_val == "已全选" or param_obj_val.lower() == "all"
                is_na = param_obj_val in ["N/A", "---", "", "/"]

                if is_all_explicit or is_na:
                     search_term = ""
                     if routine_control_type_val and ":" in routine_control_type_val:
                         search_term = routine_control_type_val.split(":")[1].strip()
                     elif routine_control_type_val:
                         search_term = routine_control_type_val.strip()

                     if is_na and search_term:
                         target_items = [
                             item for item in options_array
                             if search_term.lower() in item.get("sub_data_name_c", "").lower() or
                                search_term.lower() in item.get("sub_data_name_e", "").lower()
                         ]

                     if not target_items:
                         # Default ALL logic (excluding reserved)
                         target_items = [
                             item for item in options_array
                             if "reserved" not in item.get("sub_data_name_c", "").lower() and \
                                "预留" not in item.get("sub_data_name_c", "") and \
                                "reserved" not in item.get("sub_data_name_e", "").lower()
                         ]
                else:
                     names = [n.strip() for n in param_obj_val.split(',')]
                     for name in names:
                         for item in options_array:
                             if name in item.get("sub_data_name_c", "") or \
                                name in item.get("sub_data_name_e", ""):
                                 target_items.append(item)
                                 break

                if not target_items:
                     _log(f"未在 Options 中找到匹配参数对象: {param_obj_val}")
                     return False

                for item in target_items:
                     try:
                         target_val = -1
                         conversions = []
                         conv_c = str(item.get("conversion_c", ""))
                         conv_e = str(item.get("conversion_e", ""))
                         if conv_c and conv_c != "-" and conv_c.lower() != "nan": conversions.extend(conv_c.split('\n'))
                         if conv_e and conv_e != "-" and conv_e.lower() != "nan": conversions.extend(conv_e.split('\n'))

                         for entry in conversions:
                             if '=' not in entry: continue
                             code_str, desc = entry.split('=', 1)
                             code_str = code_str.strip()
                             desc = desc.strip()
                             if param_state_val == desc:
                                 try: target_val = int(code_str, 16) if code_str.lower().startswith("0x") else int(code_str); break
                                 except: pass
                             elif desc and desc == param_state_val:
                                 try: target_val = int(code_str, 16) if code_str.lower().startswith("0x") else int(code_str); break
                                 except: pass
                             elif param_state_val == code_str:
                                 try: target_val = int(code_str, 16) if code_str.lower().startswith("0x") else int(code_str); break
                                 except: pass

                         if target_val == -1:
                              neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "0"]
                              pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON", "1"]
                              if any(k in param_state_val for k in neg_keys): target_val = 0
                              elif any(k in param_state_val for k in pos_keys): target_val = 1
                              else:
                                  try: target_val = int(param_state_val, 16) if param_state_val.lower().startswith("0x") else int(param_state_val)
                                  except: pass

                         if target_val == -1:
                              _log(f"无法解析参数状态值: {param_state_val} (Item: {item.get('sub_data_name_c')})")
                              continue

                         byte_val = item.get("byte", 0)
                         if isinstance(byte_val, str) and byte_val.startswith("#"):
                             byte_idx = int(byte_val[1:]) - 5
                         else:
                             byte_idx = int(byte_val)

                         if byte_idx < 0 or byte_idx >= len(final_bytes):
                              _log(f"Byte index out of range: {byte_idx}")
                              continue

                         bit_def = str(item.get("bit", ""))
                         current_val = final_bytes[byte_idx]
                         start_bit = 0

                         if "~" in bit_def:
                              parts = bit_def.split("~")
                              start_bit = min(int(parts[0]), int(parts[1]))
                         else:
                              try: start_bit = int(bit_def)
                              except: start_bit = 0

                         if target_val > 0:
                             current_val |= (target_val << start_bit)
                             final_bytes[byte_idx] = current_val

                     except Exception as e:
                         _log(f"Error processing item bits: {e}")

                hex_result = final_bytes.hex(' ').upper()
                bin_result = ''.join(f'{b:08b}' for b in final_bytes)
                _log(f"[{did_key}] Routine数据计算结果: {hex_result} (Bin: {bin_result})")

        # 6. Send UDS Command
        try:
            service_hex_str = service_info.get('request', {}).get('service', '0x31').replace("0x", "")
            sid_bytes = bytes.fromhex(service_hex_str)
            did_rid_bytes = bytes.fromhex(did_key.replace("0x", ""))

            # SubFunction / IOCP
            if control_type_int != -1:
                control_byte = bytes([control_type_int])
            else:
                config_sub = service_info.get('request', {}).get('subFunction', '00').replace("0x", "")
                control_byte = bytes.fromhex(config_sub)

            if is_2f_service:
                # 2F Format: SID (2F) + DID + IOCP + [Data]
                command = sid_bytes + did_rid_bytes + control_byte + final_bytes
            else:
                 # 31 Format: SID (31) + SubFunc + RID + [Data]
                command = sid_bytes + control_byte + did_rid_bytes + final_bytes

            _log(f"发送 Routine 指令: {command.hex(' ').upper()}")

            resp = self._device_service.execute_secure_routine(command, sec_level=0x01, log_signal=self.log_signal)

            expected_resp_sid = sid_bytes[0] + 0x40
            if resp and resp[0] == expected_resp_sid:
                 _log("执行成功")
                 return True
            else:
                 _log(f"执行失败: {resp.hex(' ').upper() if resp else '无响应'}")
                 return False

        except Exception as e:
            _log(f"指令构造异常: {e}")
            return False

    def get_config_path(self, config_type: str) -> str:
        """获取配置路径"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if not settings:
            settings = {}

        if config_type == "2E":
            return settings.get("last_2e_config_path", "")
        elif config_type == "ROUTINE":
            return settings.get("last_routine_config_path", "")
        elif config_type == "DPT_2E":
            return settings.get("last_dpt_2e_path", "")
        elif config_type == "DPT_ROUTINE":
            return settings.get("last_dpt_routine_path", "")
        return ""

    def save_config_path(self, config_type: str, path: str):
        """保存配置路径"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings is None:
            settings = {}

        if config_type == "2E":
            settings["last_2e_config_path"] = path
        elif config_type == "ROUTINE":
            settings["last_routine_config_path"] = path
        elif config_type == "DPT_2E":
            settings["last_dpt_2e_path"] = path
        elif config_type == "DPT_ROUTINE":
            settings["last_dpt_routine_path"] = path

        self._system_config_service.save_json(self._config_name, settings)

    def save_system_config(self, key: str, value: str):
        """保存系统配置"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings is None:
            settings = {}
        settings[key] = value
        self._system_config_service.save_json(self._config_name, settings)

    def get_system_config(self, key: str) -> Optional[str]:
        """获取系统配置"""
        settings = self._system_config_service.load_json(self._config_name, default={})
        if settings:
             return settings.get(key)
        return None
