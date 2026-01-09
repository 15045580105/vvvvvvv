import logging
from typing import List, Dict, Any, Optional, Callable
from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService as SystemConfigService
from app.core.dependency_injection import di_container
from app.services.diagnostic.dpt_service import DPTService

logger = logging.getLogger(__name__)

class CommonConfigService:
    def __init__(self):
        self._device_service: Optional[DeviceService] = None
        self._system_config_service = SystemConfigService()
        self._dpt_service = DPTService()
        self._config_name = "common_config_settings"


    def _get_dpt_service(self) -> Optional[DPTService]:
        """获取 DPTService 实例"""
        if not self._dpt_service:
            # 优先从 DeviceService 获取，因为那里可能有已经初始化的实例
            if self._device_service and hasattr(self._device_service, 'dpt_service') and self._device_service.dpt_service:
                self._dpt_service = self._device_service.dpt_service

            # 如果没有，尝试从容器获取
            if not self._dpt_service:
                self._dpt_service = di_container.resolve(DPTService)

        return self._dpt_service

    def inject_device_service(self, device_service: DeviceService):
        self._device_service = device_service

    def get_common_params(self) -> List[Dict[str, Any]]:
        """
        获取常用参数列表
        这里可以从配置文件加载，或者硬编码一些常用参数
        """
        return [
            {"name": "VIN码", "did": "F190", "value": ""},
            {"name": "ECU硬件版本号", "did": "F191", "value": ""},
            {"name": "ECU软件版本号", "did": "F195", "value": ""},
            {"name": "系统名称", "did": "F197", "value": ""},
            {"name": "维修站代码", "did": "F198", "value": ""},
            {"name": "编程日期", "did": "F199", "value": ""},
        ]

    def get_common_routines(self) -> List[Dict[str, Any]]:
        """
        获取常用例程列表
        """
        return [
            {"name": "ECU复位", "rid": "1101", "status": "未执行"},
            {"name": "恢复出厂设置", "rid": "1103", "status": "未执行"},
        ]

    def read_param(self, did: str, log_callback: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """读取参数值"""
        if not self._device_service:
            if log_callback: log_callback("设备服务未连接")
            return None

        client = self._device_service.get_doip_client()
        if not client:
            if log_callback: log_callback("DoIP客户端未连接")
            return None

        try:
            did_int = int(did, 16)
            did_bytes = did_int.to_bytes(2, 'big')
        except ValueError:
            if log_callback: log_callback(f"无效的DID: {did}")
            return None

        # 22 DID
        cmd = bytes([0x22]) + did_bytes
        if log_callback: log_callback(f"发送读取指令: {cmd.hex(' ').upper()}")

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

            if log_callback: log_callback(f"读取成功: {val_str}")
            return val_str
        else:
            err = resp.hex(' ').upper() if resp else "无响应"
            if log_callback: log_callback(f"读取失败: {err}")
            return None

    def write_param(self, did: str, value: str, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """写入参数值 (需要实现具体逻辑，通常涉及2E服务)"""
        # 这里只是一个示例，具体写入逻辑取决于数据类型和格式
        if log_callback: log_callback(f"写入功能尚未实现: DID={did}, Value={value}")
        return False

    def execute_routine(self, rid: str, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """执行例程"""
        if not self._device_service:
            if log_callback: log_callback("设备服务未连接")
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
            if log_callback: log_callback(f"无效的RID: {rid}")
            return False

        # 使用 execute_secure_routine 来处理安全访问（如果需要）
        # 这里假设常用例程可能需要安全访问
        if log_callback: log_callback(f"发送执行指令: {cmd.hex(' ').upper()}")

        # 注意：execute_secure_routine 返回的是响应bytes或False
        # 这里我们假设 sec_level=0x01 (根据之前的代码)
        resp = self._device_service.execute_secure_routine(cmd, sec_level=0x01, log_callback=log_callback)

        if resp:
            # 检查响应
            # 11服务响应是 51
            # 31服务响应是 71
            if cmd[0] == 0x11 and resp[0] == 0x51:
                if log_callback: log_callback("执行成功")
                return True
            elif cmd[0] == 0x31 and resp[0] == 0x71:
                if log_callback: log_callback("执行成功")
                return True
            else:
                if log_callback: log_callback(f"执行失败，响应: {resp.hex(' ').upper()}")
                return False
        else:
            if log_callback: log_callback("执行失败")
            return False

    def execute_2e_service(self, service_info: Dict[str, Any], log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """执行 2E 服务"""
        if not self._device_service:
            if log_callback: log_callback("设备服务未连接")
            return False

        # 处理配置化请求
        req_config = service_info.get("requestConfig", {})
        if not req_config:
            if log_callback: log_callback("未找到请求配置")
            return False

        # 获取参数值
        p_obj_val = service_info.get("paramObject_val", "")
        p_state_val = service_info.get("paramState_val", "")

        # 构建指令
        did_str = req_config.get("dataIdentifier", "")
        if not did_str:
             if log_callback: log_callback("配置错误: 缺少 DID")
             return False

        try:
            did_int = int(did_str, 16)
            did_bytes = did_int.to_bytes(2, 'big')
        except:
             if log_callback: log_callback(f"无效的 DID: {did_str}")
             return False

        # 计算参数值
        payload = b""
        source = req_config.get("paramValueSource", "raw")

        if source == "calculated":
            # 这里需要根据具体的业务逻辑将下拉框选项映射为数值
            # 简化处理：假设选项索引或特定映射
            # 实际项目中可能需要更复杂的映射表
            # 示例：根据 paramState_val (关闭/打开) 映射为 00/01
            val_byte = 0x00
            if "打开" in p_state_val:
                val_byte = 0x01
            elif "关闭" in p_state_val:
                val_byte = 0x00
            # --- 新增: paramObject_val 的 IP 地址解析与小端序转换 ---
            # 如果配置中 explicit_type 指明了是 "ip_le" (Little Endian IP) / "ip_be" / "u16_le" 等
            # 或者根据 paramObject 类型自动推断。这里假设 JSON 中可能会指定 "conversion": "ip_le"

            conversion = req_config.get("conversion", "")

            if conversion == "ip_le":
                # 解析 IP 地址为小端序 (e.g. 192.168.1.10 -> C0 A8 01 0A -> 0A 01 A8 C0)
                # 检查 p_obj_val 是否看起来像 IP
                import socket
                try:
                    # socket.inet_aton 将 IP 字符串转为 bytes (大端序/网络序)
                    ip_bytes = socket.inet_aton(p_obj_val)
                    # 反转为小端序
                    payload = ip_bytes[::-1]
                except Exception as e:
                    if log_callback: log_callback(f"IP 解析失败: {e}")
                    return False
            elif conversion == "u32_le":
                 try:
                     val = int(p_obj_val)
                     payload = val.to_bytes(4, 'little')
                 except:
                     pass
            elif conversion == "u16_le":
                 try:
                     val = int(p_obj_val)
                     payload = val.to_bytes(2, 'little')
                 except:
                     pass
            else:
                # 缺省简单逻辑
                payload = bytes([val_byte])

        elif source == "ascii":
            # 字符串转 ASCII
            length = req_config.get("paramValueLength", 0)
            try:
                payload = p_obj_val.encode('ascii')
                if length > 0:
                    payload = payload.ljust(length, b'\x00')[:length]
            except:
                if log_callback: log_callback("参数转换 ASCII 失败")
                return False

        elif source == "raw":
             try:
                payload = bytes.fromhex(p_obj_val.replace(" ", ""))
             except:
                if log_callback: log_callback("无效的 Hex 格式")
                return False

        # 组装最终指令: 2E + DID + Payload
        cmd_bytes = bytes([0x2E]) + did_bytes + payload

        if log_callback: log_callback(f"发送指令: {cmd_bytes.hex(' ').upper()}")

        resp = self._device_service.execute_secure_routine(cmd_bytes, sec_level=0x01, log_callback=log_callback)

        if resp:
            expected_head = 0x6E
            if resp[0] == expected_head:
                if log_callback: log_callback("执行成功")
                return True
            else:
                if log_callback: log_callback(f"执行失败，响应: {resp.hex(' ').upper()}")
                return False
        else:
            return False



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

    def execute_routine_service(self, service_info: Dict[str, Any], log_callback: Callable[[str], None] = None) -> bool:
        """执行 $31 / $2F 服务 (适配 View 闭包调用)"""
        # 兼容旧代码，这里直接调用 execute_routine_v2
        # 注意：View 中传递的 service_info 已经包含了 paramObject_val 和 paramState_val (如果是 CheckableComboBox 动态绑定的)
        # 如果没有值，则默认为 '---'
        
        param_obj_val = service_info.get("paramObject_val", "---")
        param_state_val = service_info.get("paramState_val", "---")
        
        return self.execute_routine_v2(service_info, param_obj_val, param_state_val, log_callback)

    def execute_routine_v2(self, service_info: Dict[str, Any], param_obj_val: str, param_state_val: str,
                        log_callback: Callable[[str], None] = None) -> bool:
        """
        执行 $31 / $2F 服务 (New Logic)
        :param service_info: 服务配置信息 (JSON 加载的 item)
        :param param_obj_val: 界面上选择的“参数对象”值
        :param param_state_val: 界面上选择的“参数状态”值
        :param log_callback: 日志回调
        """
        def _log(msg: str):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        if not self._device_service:
            _log("错误: DeviceService 未就绪")
            return False

        # 1. 获取 requestConfig
        req_config = service_info.get("requestConfig")
        if not req_config:
            _log("错误: 未找到 requestConfig 配置")
            return False

        service_id_hex = req_config.get("service")       # "0x31" or "0x2F"
        data_identifier_hex = req_config.get("dataIdentifier") # DID
        # sub_function_hex = req_config.get("subFunction")       # "0x01", "0x03" etc.

        if not service_id_hex or not data_identifier_hex:
             _log("错误: 配置缺少 service 或 dataIdentifier")
             return False

        # 2. 准备 DPT 参数以获取 payload
        service_id = service_info.get("serviceId", data_identifier_hex) # 用来查找 DPT 的 Key，通常是 DID，但 Config 中有时叫 serviceId

        _log(f"准备执行 {service_info.get('content', '未知服务')}")
        _log(f"参数对象: {param_obj_val}, 参数状态: {param_state_val}")

        # 调用 DPT Service 获取 Payload
        dpt_service = self._dpt_service

        if not dpt_service:
             _log("错误: 无法获取 DPTService，将尝试使用降级逻辑")
             # return False # 不返回 False，尝试降级逻辑

        payload_bytes = None
        if dpt_service:
            try:
                # 调用 DPT Service 组装数据
                payload_bytes = dpt_service.get_did_data(service_id)
            except Exception as e:
                _log(f"DPT 数据组装异常: {e}")
                # return False

        # 如果 DPT 返回 None (通常是因为没有配置或实现)，尝试降级逻辑
        if not payload_bytes:
             # Fallback logic in case DPT service returns None
             payload = b""
             # 简单处理：假设选项索引或特定映射
             # 实际项目中可能需要更复杂的映射表
             # 示例：根据 paramState_val (关闭/打开) 映射为 00/01
             val_byte = 0x00
             if "打开" in param_state_val or "使能" in param_state_val:
                 val_byte = 0x01
             elif "关闭" in param_state_val or "禁止" in param_state_val:
                 val_byte = 0x00

             # 特殊 case: 31/2F 服务的 Payload 结构
             # 通常是 Service(1B) + SubFunction(1B) + DID(2B) + ControlOptionRecord(...)
             # 但这里的 payload 变量目前只计算了 ControlOptionRecord 部分

             # --- 新增: paramObject_val 的 IP 地址解析与小端序转换 ---
             # 如果配置中 explicit_type 指明了是 "ip_le" (Little Endian IP) / "ip_be" / "u16_le" 等
             # 或者根据 paramObject 类型自动推断。这里假设 JSON 中可能会指定 "conversion": "ip_le"

             conversion = req_config.get("conversion", "")

             if conversion == "ip_le":
                 # 解析 IP 地址为小端序 (e.g. 192.168.1.10 -> C0 A8 01 0A -> 0A 01 A8 C0)
                 # 检查 p_obj_val 是否看起来像 IP
                 import socket
                 try:
                     # socket.inet_aton 将 IP 字符串转为 bytes (大端序/网络序)
                     ip_bytes = socket.inet_aton(param_obj_val)
                     # 反转为小端序
                     payload = ip_bytes[::-1]
                 except Exception as e:
                     if log_callback: log_callback(f"IP 解析失败: {e}")
                     return False
             elif conversion == "u32_le":
                  try:
                      val = int(param_obj_val)
                      payload = val.to_bytes(4, 'little')
                  except:
                      pass
             elif conversion == "u16_le":
                  try:
                      val = int(param_obj_val)
                      payload = val.to_bytes(2, 'little')
                  except:
                      pass
             else:
                 # 缺省简单逻辑
                 payload = bytes([val_byte])

             # 重新组装完整的 UDS Request (Service + SubFunc + DID + Data)
             # execute_secure_routine 通常需要完整的指令

             try:
                 sid_int = int(service_id_hex, 16)
                 did_int = int(data_identifier_hex, 16)
                 did_bytes = did_int.to_bytes(2, 'big')

                 sub_func_str = req_config.get("subFunction")
                 if sub_func_str:
                     sub_func_int = int(sub_func_str, 16)
                     payload_bytes = bytes([sid_int, sub_func_int]) + did_bytes + payload
                 else:
                     # 2E 服务没有 SubFunction
                     if sid_int == 0x2E:
                         payload_bytes = bytes([sid_int]) + did_bytes + payload
                     else:
                         # 默认情况尝试加 subfunction? 或者直接拼
                         payload_bytes = bytes([sid_int]) + did_bytes + payload

             except Exception as e:
                 _log(f"指令组装失败: {e}")
                 return False

             # 如果降级逻辑也无法处理，返回错误
             if not payload_bytes:
                 _log(f"错误: 无法生成 Payload (ServiceId={service_id})")
                 return False

        _log(f"生成指令 Payload: {payload_bytes.hex(' ').upper()}")

        # 3. 发送指令
        # 区分是 2E, 31, 2F
        # 31 使用 execute_secure_routine (带安全访问)
        # 2F 使用 IO Control (也可能带安全访问)
        # 这里统一根据是否需要 security 来决定
        
        success = False
        
        # 使用 execute_secure_routine 统一处理 (支持 10 03 -> 27 -> Payload)
        # 默认 sec_level = 0x01，如果 JSON 指定了 SecurityLevel 也可以读取
        result = self._device_service.execute_secure_routine(payload_bytes, sec_level=0x01, log_callback=_log)
        
        # 4. 解析结果 (Result Mapping)
        # 如果 result 是 bytes，说明有响应
        if isinstance(result, bytes) and result:
             # 简单检查肯定响应
             # expected: ServiceID + 0x40
             expected_origin_sid = payload_bytes[0]
             expected_resp_sid = expected_origin_sid + 0x40
             
             if result[0] == expected_resp_sid:
                  _log(f"收到肯定响应: {result.hex(' ').upper()}")
                  success = True
                  
                  # 尝试解析结果 (Result Mapping)
                  mapping = req_config.get("resultMapping")
                  if mapping:
                       # 简单逻辑：如果成功，且 mapping 含 "成功"，则打印
                       pass
             else:
                 # 否定响应 7F ...
                 if result[0] == 0x7F:
                     if len(result) >= 3:
                         nrc = result[2]
                         _log(f"收到否定响应 (NRC={nrc:02X}): {result.hex(' ').upper()}")
                     else:
                         _log(f"收到否定响应: {result.hex(' ').upper()}")
                 else:
                     _log(f"收到意外响应: {result.hex(' ').upper()}")
                 success = False
        else:
             if result is False:
                 # execute_secure_routine 内部已经 log 了错误
                 pass
             else:
                 _log("未收到有效响应")
             success = False

        return success
