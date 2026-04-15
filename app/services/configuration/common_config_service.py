import logging
import re
from typing import List, Dict, Any, Optional
from PyQt5.QtCore import QObject, pyqtSignal

from app.services.device_manage.device_service import DeviceService
from app.services.system.config_service import ConfigService as SystemConfigService
import json
import os

logger = logging.getLogger(__name__)


class CommonConfigService(QObject):
    """常用服务运行期服务层。

    职责分成两段：
    1. 把 Excel 转出来的 JSON 标准化成界面可直接渲染的 service_info；
    2. 在用户完成表格选择后，根据 JSON 中的 byte/bit 与状态映射拼出 UDS 指令。
    """
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._device_service: Optional[DeviceService] = None
        self._system_config_service = SystemConfigService()
        self._config_name = "common_config_settings"
        self._shared_config_key = "last_common_service_config_path"

    def _emit_log(self, message: str) -> None:
        """统一输出运行日志，兼容静态检查并避免散落的 signal.emit 调用。"""
        emit = getattr(self.log_signal, "emit", None)
        if callable(emit):
            emit(message)

    def inject_device_service(self, device_service: DeviceService):
        self._device_service = device_service

    def execute_2e_service(self, service_info):
        _log = self._emit_log
        if not self._device_service:
            _log("设备服务未连接")
            return False

        if self._is_raw_custom_2e_request(service_info):
            raw_command = self._build_raw_custom_2e_command(service_info)
            if raw_command is None:
                _log("自定义 2E 请求为空或格式非法，请输入完整十六进制 UDS 报文")
                return False

            _log(f"发送自定义 2E 指令: {raw_command.hex(' ').upper()}")
            resp = self._device_service.execute_secure_routine(raw_command, sec_level=0x01, log_signal=self.log_signal)
            if resp and resp[0] == 0x6E:
                _log("执行成功")
                return True
            _log(f"执行失败: {resp.hex(' ').upper() if resp else '无响应'}")
            return False

        service_hex = self._normalize_hex(self._get_service_did(service_info))
        if not service_hex:
            _log("未配置有效的 Service ID / DID")
            return False

        payload = self._build_request_payload(
            service_info,
            service_info.get("paramObject_val", "---"),
            service_info.get("paramState_val", "---"),
        )
        if payload is None:
            _log("无法根据当前参数和配置构造 2E 请求数据")
            return False

        try:
            command = bytes([0x2E]) + bytes.fromhex(service_hex) + payload
        except Exception as e:
            _log(f"构造 2E 指令失败: {e}")
            return False

        _log(f"发送指令: {command.hex(' ').upper()}")
        resp = self._device_service.execute_secure_routine(command, sec_level=0x01, log_signal=self.log_signal)
        if resp and resp[0] == 0x6E:
            _log("执行成功")
            return True
        _log(f"执行失败: {resp.hex(' ').upper() if resp else '无响应'}")
        return False

    def _is_raw_custom_2e_request(self, service_info: Optional[Dict[str, Any]]) -> bool:
        """识别“用户直接输入完整 UDS 报文”的自定义 2E 行。"""
        # 运行期优先读取显式 schema（`rawRequest` / `source=manual`）；
        # 只有老 JSON 没升级时，才退回到“缺 DID + String/Input”这类兼容推断。
        if not isinstance(service_info, dict):
            return False

        sid_hex = self._normalize_hex(self._get_service_sid(service_info), 1)
        if sid_hex != "2E":
            return False

        if bool(service_info.get("rawRequest")):
            return True

        source = str(service_info.get("source") or "").strip().lower()
        if source in {"manual", "raw", "direct", "full_request"}:
            return True

        did_text = str(service_info.get("did") or "").strip()
        param_object = service_info.get("paramObject") or {}
        param_object_type = str(param_object.get("type") or "").strip().lower() if isinstance(param_object, dict) else ""
        validation = str(param_object.get("validation") or "").strip().lower() if isinstance(param_object, dict) else ""
        content_text = str(service_info.get("content") or "").strip().lower()

        missing_did = did_text in {"", "/", "---", "n/a"}
        string_input_like = param_object_type == "input" or validation in {"string", "raw", "hex", "uds"}
        return missing_did and (string_input_like or "自定义2e" in content_text)

    def _build_raw_custom_2e_command(self, service_info: Dict[str, Any]) -> Optional[bytes]:
        """把参数对象输入框中的十六进制文本直接转成完整 UDS 请求。"""
        raw_text = service_info.get("paramObject_val", "")
        command = self._parse_hex_command_text(raw_text)
        if not command:
            return None

        if command[0] != 0x2E:
            self._emit_log("自定义 2E 请求必须以 2E 开头，例如：2E 01 03 00")
            return None
        return command

    def _parse_hex_command_text(self, raw_value: Any) -> Optional[bytes]:
        """把类似 `2E 01 03 00` / `0x2E 0x01 0x03 0x00` 的输入解析成 bytes。"""
        if raw_value is None:
            return None

        text = str(raw_value).strip()
        if text in {"", "---", "/", "N/A"}:
            return None

        normalized = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        normalized = re.sub(r"0x", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"[^0-9A-Fa-f]", "", normalized)
        if not normalized:
            return None
        if len(normalized) % 2 != 0:
            self._emit_log(f"十六进制报文长度非法，请检查输入: {text}")
            return None
        try:
            return bytes.fromhex(normalized)
        except ValueError:
            self._emit_log(f"十六进制报文格式非法，请检查输入: {text}")
            return None

    def load_2e_config(self, file_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(file_path):
            logger.error(f"配置文件不存在: {file_path}")
            return []
        try:
            data = self._load_json_file(file_path)
            services = self._extract_services_by_type(data, "2E")
            return [self._normalize_2e_service(service, index) for index, service in enumerate(services, start=1)]
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return []

    def load_shared_config(self, file_path: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """加载统一 JSON，并拆成 `$2E` 与 `$31/$2F` 两组给两个标签页使用。

        这是 JSON -> 界面表格 的主要入口：
        - `services_2e` 会渲染到“常用 $2E 服务”表格
        - `services_routine` 会渲染到“常用 $31&$2F 服务”表格
        """
        if not os.path.exists(file_path):
            logger.error(f"配置文件不存在: {file_path}")
            return [], []
        data = self._load_json_file(file_path)
        services_2e = [
            self._normalize_2e_service(service, index)
            for index, service in enumerate(self._extract_services_by_type(data, "2E"), start=1)
        ]
        services_routine = [
            self._normalize_routine_service(service, index)
            for index, service in enumerate(self._extract_services_by_type(data, "ROUTINE"), start=1)
        ]
        return services_2e, services_routine

    def save_last_2e_config_path(self, file_path: str):
        self.save_config_path("2E", file_path)

    def get_last_2e_config_path(self) -> Optional[str]:
        return self.get_config_path("2E") or None

    def load_routine_config(self, file_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(file_path):
            logger.error(f"配置文件不存在: {file_path}")
            return []
        try:
            data = self._load_json_file(file_path)
            services = self._extract_services_by_type(data, "ROUTINE")
            return [self._normalize_routine_service(service, index) for index, service in enumerate(services, start=1)]
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return []

    def save_last_routine_config_path(self, file_path: str):
        self.save_config_path("ROUTINE", file_path)

    def get_last_routine_config_path(self) -> Optional[str]:
        return self.get_config_path("ROUTINE") or None

    def execute_routine_service(self, service_info: Dict[str, Any]) -> bool:
        return self.execute_routine_v2(
            service_info,
            service_info.get("paramObject_val", "---"),
            service_info.get("paramState_val", "---"),
            service_info.get("routineControlType_val", "---"),
        )

    def execute_routine_v2(self, service_info: Dict[str, Any], param_obj_val: str, param_state_val: str, routine_control_type_val: str) -> bool:
        _log = self._emit_log
        if not self._device_service or not self._device_service.get_doip_client():
            _log("设备未连接 (DoIP)，无法执行服务")
            return False

        sid_hex = self._normalize_hex(self._get_service_sid(service_info), 1)
        did_hex = self._normalize_hex(self._get_service_did(service_info))
        if not sid_hex or not did_hex:
            _log("配置错误: 缺少 service 或 DID")
            return False

        control_hex = self._resolve_control_hex(routine_control_type_val, self._get_sub_function(service_info))
        if control_hex is None:
            _log("无法解析例程控制类型")
            return False

        payload = self._build_request_payload(service_info, param_obj_val, param_state_val, routine_control_type_val)
        if payload is None:
            _log("无法根据当前参数和配置构造请求数据")
            return False

        try:
            sid_bytes = bytes.fromhex(sid_hex)
            did_bytes = bytes.fromhex(did_hex)
            control_bytes = bytes.fromhex(control_hex)
            # `$2F` 的报文顺序是 SID + DID + control + payload；
            # `$31` 的报文顺序是 SID + control + RID + payload。
            command = sid_bytes + did_bytes + control_bytes + payload if sid_bytes == b'\x2f' else sid_bytes + control_bytes + did_bytes + payload
        except Exception as e:
            _log(f"指令构造异常: {e}")
            return False

        _log(f"发送 Routine 指令: {command.hex(' ').upper()}")
        resp = self._device_service.execute_secure_routine(command, sec_level=0x01, log_signal=self.log_signal)
        expected_resp_sid = sid_bytes[0] + 0x40
        if resp and resp[0] == expected_resp_sid:
            _log("执行成功")
            return True
        _log(f"执行失败: {resp.hex(' ').upper() if resp else '无响应'}")
        return False

    def _load_json_file(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return json.loads(self._sanitize_json_hex_literals(raw_text))

    def _sanitize_json_hex_literals(self, raw_text: str) -> str:
        return re.sub(
            r'(?<=[\[,])\s*0x([0-9A-Fa-f]+)\s*(?=[,\]])',
            lambda m: str(int(m.group(1), 16)),
            raw_text,
        )

    def _normalize_routine_service(self, service: Dict[str, Any], default_index: int) -> Dict[str, Any]:
        """把 JSON 中的 `$31/$2F` 原始定义标准化成界面运行期数据。

        标准化后，界面无需关心 Excel 原始格式，只关心统一字段：
        `did/service/subFunction/paramObject/paramState/routineControlType/`
        `payloadDefinition/controlDefinitions`。
        """
        normalized = dict(service)
        normalized["index"] = normalized.get("index", default_index)
        normalized["did"] = self._get_service_did(normalized) or ""
        normalized["service"] = self._get_service_sid(normalized) or ""
        normalized["subFunction"] = self._get_sub_function(normalized) or ""
        normalized["payloadDefinition"] = self._normalize_payload_definition(normalized)
        normalized["controlDefinitions"] = self._normalize_control_definitions(normalized)
        normalized["paramObject"] = self._normalize_field_config(normalized.get("paramObject"), "N/A", normalized, "paramObject")
        normalized["paramState"] = self._normalize_field_config(normalized.get("paramState"), "N/A", normalized, "paramState")

        routine_control = normalized.get("routineControlType")
        if not routine_control:
            fallback_sub = self._get_sub_function(normalized)
            routine_control = {"value": str(fallback_sub or "N/A")}
        normalized["routineControlType"] = self._normalize_field_config(routine_control, "N/A", normalized, "routineControlType")

        if normalized["routineControlType"].get("type") == "dropdown":
            options = normalized["routineControlType"].get("options") or []
            if options and not normalized["routineControlType"].get("default"):
                normalized["routineControlType"]["default"] = options[0]

        normalized["request"] = self._normalize_request_config(normalized)
        normalized["paramByteLength"] = self._safe_int(normalized["request"].get("paramByteLength"), 0)
        normalized["source"] = normalized["request"].get("source", "")
        return normalized

    def _normalize_2e_service(self, service: Dict[str, Any], default_index: int) -> Dict[str, Any]:
        """把 JSON 中的 `$2E` 原始定义标准化成界面运行期数据。"""
        normalized = dict(service)
        normalized["index"] = normalized.get("index", default_index)
        normalized["did"] = self._get_service_did(normalized) or ""
        normalized["service"] = self._get_service_sid(normalized) or "0x2E"
        normalized["subFunction"] = self._get_sub_function(normalized) or "00"
        normalized["payloadDefinition"] = self._normalize_payload_definition(normalized)
        normalized["controlDefinitions"] = self._normalize_control_definitions(normalized)
        normalized["paramObject"] = self._normalize_field_config(normalized.get("paramObject"), "N/A", normalized, "paramObject")
        normalized["paramState"] = self._normalize_field_config(normalized.get("paramState"), "N/A", normalized, "paramState")
        normalized["request"] = self._normalize_request_config(normalized)
        normalized["paramByteLength"] = self._safe_int(normalized["request"].get("paramByteLength"), 0)
        normalized["source"] = normalized["request"].get("source", "")
        return normalized

    def _normalize_request_config(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """兼容旧/新 JSON 结构，整理出统一 request 视图。

        现在顶层字段已经以 `did/service/subFunction/...` 为主，
        但这里仍保留一层 `request` 归一化结果，便于兼容旧配置和旧调用点。
        """
        request = dict(service.get("request") or {})
        service_sid = self._get_service_sid(service)
        sub_function = self._get_sub_function(service)
        did = self._get_service_did(service)
        param_byte_length = service.get("paramByteLength", request.get("paramByteLength", 0))
        if service_sid:
            request["service"] = service_sid
        if sub_function not in [None, ""]:
            request["subFunction"] = sub_function
        if did:
            request["dataIdentifier"] = did
        request["paramByteLength"] = self._safe_int(param_byte_length, 0)

        # 新 schema 里，普通服务通常不再持久化 `source`，这里统一在运行期补回；
        # 对 raw/custom 直发场景，则优先从 `rawRequest` 还原为 `manual`。
        source = str(service.get("source") or request.get("source", "")).strip().lower()
        if not source and bool(service.get("rawRequest")):
            source = "manual"
        if not source:
            source = self._infer_request_source_from_service(service)
        request["source"] = source

        return request

    def _infer_request_source_from_service(self, service: Dict[str, Any]) -> str:
        # `rawRequest` 是唯一不能靠 payloadDefinition 完全替代的行为开关：
        # 它表示“参数对象输入框里就是整条 UDS 报文，需要原样发送”。
        if bool(service.get("rawRequest")):
            return "manual"
        payload_mode = self._get_payload_mode(service)
        if payload_mode == "ascii":
            return "ascii"
        if payload_mode in {"bitfield", "identity"}:
            return "calculated"
        if self._is_input_field(service.get("paramObject")) or self._is_input_field(service.get("paramState")):
            return "ascii"
        if self._safe_int(service.get("paramByteLength", (service.get("request") or {}).get("paramByteLength")), 0) <= 0:
            return "fixed"
        return "calculated"

    def _is_input_field(self, config: Any) -> bool:
        return isinstance(config, dict) and str(config.get("type", "")).strip().lower() == "input"

    def _normalize_field_config(self, config: Any, default_fixed_value: str, service: Optional[Dict[str, Any]] = None, field_name: str = "") -> Dict[str, Any]:
        """把 JSON 字段配置归一化成界面控件可直接消费的结构。

        最终会落到三类控件：
        - fixed -> 表格只读文本
        - dropdown/checkabledropdown -> 下拉框/复选下拉
        - input -> 输入框
        """
        if isinstance(config, dict):
            normalized = dict(config)
            if self._should_use_na_fixed_field(normalized, field_name):
                return {"type": "fixed", "value": self._derive_fixed_value(service, field_name, default_fixed_value)}
            field_type = normalized.get("type") or self._infer_field_type(normalized, service, field_name)
            normalized["type"] = field_type
            if field_type in {"dropdown", "checkabledropdown"}:
                normalized["options"] = [str(option) for option in (normalized.get("options") or self._derive_field_options(normalized, service, field_name)) if str(option).strip()]
                if not normalized["options"]:
                    return {"type": "fixed", "value": self._derive_fixed_value(service, field_name, default_fixed_value)}
                if field_type == "dropdown" and normalized["options"] and not normalized.get("default"):
                    normalized["default"] = normalized["options"][0]
                if field_type == "checkabledropdown" and "default" not in normalized:
                    normalized["default"] = "---"
            elif field_type == "input":
                normalized.setdefault("placeholder", self._derive_input_placeholder(field_name))
            elif field_type == "fixed":
                normalized["value"] = str(normalized.get("value", self._derive_fixed_value(service, field_name, default_fixed_value)))
            return normalized
        if config in [None, "", "---"]:
            inferred = self._infer_field_type({}, service, field_name)
            if inferred in {"dropdown", "checkabledropdown"}:
                options = self._derive_field_options({}, service, field_name)
                default_value = options[0] if inferred == "dropdown" and options else "---"
                return {"type": inferred, "options": options, "default": default_value}
            if inferred == "input":
                return {"type": "input", "placeholder": self._derive_input_placeholder(field_name)}
            return {"type": "fixed", "value": self._derive_fixed_value(service, field_name, default_fixed_value)}
        return {"type": "fixed", "value": str(config)}

    def _extract_services_by_type(self, data: Dict[str, Any], service_group: str) -> List[Dict[str, Any]]:
        """从统一 JSON 中提取指定服务分组，并兼容若干历史 key。"""
        preferred_keys = {
            "2E": ["services2E", "services_2e", "service2E", "services2e"],
            "ROUTINE": ["services31_2F", "services_31_2f", "servicesRoutine", "services_routine", "services31and2F"],
        }
        for key in preferred_keys.get(service_group, []):
            services = data.get(key)
            if isinstance(services, list):
                return services

        services = data.get("services")
        if not isinstance(services, list):
            return []

        if service_group == "2E":
            return [service for service in services if self._service_family(service) == "2E"]
        return [service for service in services if self._service_family(service) in {"31", "2F"}]

    def _service_family(self, service: Dict[str, Any]) -> str:
        sid = self._normalize_hex(self._get_service_sid(service), 1)
        if sid == "2E":
            return "2E"
        if sid == "31":
            return "31"
        if sid == "2F":
            return "2F"
        content = str(service.get("content", "")).upper()
        if "$2F" in content:
            return "2F"
        if "$31" in content:
            return "31"
        return "2E"

    def _infer_field_type(self, config: Dict[str, Any], service: Optional[Dict[str, Any]], field_name: str) -> str:
        if config.get("type") in {"fixed", "input", "dropdown", "checkabledropdown"}:
            return str(config["type"])

        if any(key in config for key in ("placeholder", "validation", "editable", "inputHint")):
            return "input"

        options = config.get("options") or self._derive_field_options(config, service, field_name)
        if options:
            if field_name == "paramObject":
                return "checkabledropdown"
            return "dropdown"

        source = str(self._get_request_source(service or {})).strip().lower()
        if source in {"ascii", "input", "manual"} and field_name in {"paramObject", "paramState"}:
            return "input"

        return "fixed"

    def _derive_field_options(self, config: Dict[str, Any], service: Optional[Dict[str, Any]], field_name: str) -> List[str]:
        if config.get("options"):
            return [str(option) for option in config.get("options") if str(option).strip()]
        if not service:
            return []

        field_config = service.get(field_name)
        if isinstance(field_config, dict) and field_config.get("options"):
            return [str(option) for option in field_config.get("options") if str(option).strip()]

        if field_name == "routineControlType":
            fallback = str(self._get_sub_function(service) or "").strip()
            return [fallback] if fallback else []

        return []

    def _derive_input_placeholder(self, field_name: str) -> str:
        placeholders = {
            "paramObject": "请输入参数对象",
            "paramState": "请输入参数状态",
            "routineControlType": "请输入例程控制类型",
        }
        return placeholders.get(field_name, "请输入参数")

    def _derive_fixed_value(self, service: Optional[Dict[str, Any]], field_name: str, default_fixed_value: str) -> str:
        if field_name == "routineControlType" and service:
            fallback_sub = self._get_sub_function(service)
            if fallback_sub not in [None, ""]:
                return str(fallback_sub)
        return default_fixed_value

    def _build_request_payload(self, service_info: Dict[str, Any], param_obj_val: Any, param_state_val: Any, routine_control_type_val: Optional[str] = None) -> Optional[bytes]:
        """根据当前表格选择构造请求 payload。

        这是“表格选择 -> UDS payload”最核心的分发入口：
        - ascii: 输入框文本转字节
        - fixed: 直接补零
        - bitfield / identity: 从 JSON 的 byte/bit + stateMappings 计算
        """
        # 这里是“表格控件值 -> payload 字节流”的统一分发口；
        # 真正决定分支的核心字段只有：payloadDefinition.mode / paramByteLength /
        # paramObject/paramState 配置，而不是旧版 calculationType 之类描述性字段。
        control_definition = self._get_selected_control_definition(service_info, routine_control_type_val)
        payload_mode = self._get_payload_mode(service_info, control_definition)
        expected_len = self._get_effective_param_byte_length(service_info, control_definition)

        if payload_mode == "ascii":
            return self._build_input_payload(service_info, expected_len)

        if payload_mode == "fixed":
            return self._build_fixed_payload(expected_len)

        if payload_mode in {"bitfield", "identity"}:
            return self._build_calculated_payload(service_info, param_obj_val, param_state_val, expected_len, payload_mode)

        source = str(self._get_request_source(service_info)).strip().lower()
        if source in {"ascii", "input", "manual"}:
            return self._build_input_payload(service_info, expected_len)
        return self._build_fixed_payload(expected_len)

    def _build_input_payload(self, service_info: Dict[str, Any], expected_len_value: Any = None):
        """构造输入型 payload。

        `ascii` 模式下会先用 0x20 预填充目标长度，再从 byte0 开始写入输入字符的 ASCII/UTF-8 字节；
        非 ascii 输入模式则按原逻辑补 `0x00` 到目标长度。
        """
        expected_len = expected_len_value if expected_len_value is not None else service_info.get("paramByteLength", (service_info.get("request") or {}).get("paramByteLength"))
        obj_conf = service_info.get("paramObject", {}) or {}
        state_conf = service_info.get("paramState", {}) or {}
        obj_val = service_info.get("paramObject_val", "")
        state_val = service_info.get("paramState_val", "")
        source = str(self._get_request_source(service_info)).strip().lower()

        try:
            expected_len = int(expected_len) if expected_len is not None else None
        except Exception:
            expected_len = None

        payload = b"".join(part for part in [self._encode_input_part(obj_conf, obj_val), self._encode_input_part(state_conf, state_val)] if part)
        if expected_len is None:
            return payload
        if len(payload) > expected_len:
            self._emit_log(f"输入数据长度超出配置长度: {len(payload)} > {expected_len}")
            return None
        if source == "ascii":
            # ASCII 类型要求先按 payload 长度铺满 0x20，再从 byte0 开始覆盖用户输入内容。
            padded = bytearray(b'\x20' * expected_len)
            padded[:len(payload)] = payload
            return bytes(padded)
        if len(payload) < expected_len:
            payload += b'\x00' * (expected_len - len(payload))
        return payload

    def _build_fixed_payload(self, service_info: Any) -> Optional[bytes]:
        if isinstance(service_info, dict):
            expected_len = self._safe_int(service_info.get("paramByteLength", (service_info.get("request") or {}).get("paramByteLength")), 0)
        else:
            expected_len = self._safe_int(service_info, 0)
        return b"" if expected_len <= 0 else (b'\x00' * expected_len)

    def _build_calculated_payload(self, service_info: Dict[str, Any], param_obj_val: Any, param_state_val: Any, expected_len_value: Any, payload_mode: str) -> Optional[bytes]:
        """按 JSON 中的 byte/bit 映射计算 payload。

        典型流程：
        1. 从 `paramState` 当前选择解析出数值；
        2. 从 `payloadDefinition.items` 找到所选对象对应的 byte/bit；
        3. 把状态值写入对应 bit 或整个 byte；
        4. 返回最终 payload。
        """
        expected_len = self._safe_int(expected_len_value, 0)
        payload_definition = self._normalize_payload_definition(service_info)
        if expected_len <= 0:
            return b""

        state_value = self._resolve_state_numeric_value(service_info, param_state_val)
        if state_value is None:
            self._emit_log("无法从参数状态中解析出有效数值")
            return None

        payload = bytearray(expected_len)
        items = self._resolve_target_payload_items(service_info, param_obj_val, payload_definition)
        if not items and payload_mode == "bitfield":
            self._emit_log("未找到所选参数对象对应的 byte/bit 定义")
            return None
        if not items and payload_mode == "identity":
            items = [{"object": "---", "byte": 0, "bit": "All"}]

        for item in items:
            byte_index = self._safe_int(item.get("byte"), -1)
            if byte_index < 0 or byte_index >= expected_len:
                self._emit_log(f"byte 定义越界: {byte_index}")
                return None

            bit_value = item.get("bit")
            if payload_mode == "bitfield" and isinstance(bit_value, int):
                # bitfield 模式：状态值通常是 0/1，对应清零/置位某个 bit。
                if state_value:
                    payload[byte_index] |= (1 << bit_value)
                else:
                    payload[byte_index] &= ~(1 << bit_value)
                continue

            if isinstance(bit_value, int):
                # identity 场景下若仍给了 bit，也沿用按 bit 写入的逻辑。
                if state_value:
                    payload[byte_index] |= (1 << bit_value)
                else:
                    payload[byte_index] &= ~(1 << bit_value)
                continue

            payload[byte_index] = state_value & 0xFF

        return bytes(payload)

    def _encode_input_part(self, config: Dict[str, Any], value: Any) -> bytes:
        if not isinstance(config, dict) or config.get("type") != "input":
            return b""
        text = "" if value is None else str(value).strip()
        if text in {"", "---", "/", "N/A"}:
            return b""
        validation = str(config.get("validation", "")).lower()
        if validation == "ip":
            octets = text.split('.')
            if len(octets) != 4:
                self._emit_log(f"无效 IP 地址: {text}")
                return b""
            try:
                return bytes(int(o) for o in octets)
            except Exception:
                self._emit_log(f"无效 IP 地址: {text}")
                return b""
        if validation == "port":
            try:
                port = int(text)
                if not 0 <= port <= 65535:
                    raise ValueError
                return port.to_bytes(2, 'big')
            except Exception:
                self._emit_log(f"无效端口: {text}")
                return b""
        return text.encode('utf-8')

    def _resolve_control_hex(self, selected_control: Optional[str], fallback_sub_function: Optional[str]) -> Optional[str]:
        """把界面上的“例程控制类型”文本解析成真正的 control byte。

        兼容：
        - `0x03`
        - `03`
        - `执行03 Start`
        - `03: Start`
        """
        selected = self._normalize_scalar(selected_control)
        control = selected or self._normalize_scalar(fallback_sub_function)
        if control is None:
            return "00"

        candidates = [str(control).strip()]
        if selected and fallback_sub_function and str(fallback_sub_function).strip() not in candidates:
            candidates.append(str(fallback_sub_function).strip())

        for candidate in candidates:
            hex_match = re.search(r"0x([0-9A-Fa-f]+)", candidate)
            if hex_match:
                normalized = self._normalize_hex(hex_match.group(1), 1)
                if normalized:
                    return normalized

            action_match = re.search(r"执行\s*(\d+)", candidate)
            if action_match:
                try:
                    return f"{int(action_match.group(1)):02X}"
                except Exception:
                    pass

            raw = candidate.split(':', 1)[0].strip()
            normalized = self._normalize_hex(raw, 1)
            if normalized:
                return normalized
            try:
                return f"{int(raw):02X}"
            except Exception:
                continue
        return None

    def _normalize_selection_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            items = value
        else:
            text = str(value).strip()
            if text in {"", "---", "/", "N/A"}:
                return []
            if text == "已全选":
                return ["__ALL__"]
            items = [part.strip().replace("\n", "") for part in text.split(',')]
        return [item for item in items if item and item not in {"---", "/", "N/A"}]

    def _stringify_param_object(self, service_info: Dict[str, Any], value: Any) -> str:
        if isinstance(value, str):
            text = value.strip()
            if text and text not in {"---", "/", "N/A"}:
                return text
        if isinstance(value, list):
            items = self._normalize_selection_list(value)
            if items:
                return ", ".join(items)

        field_config = service_info.get("paramObject") or {}
        if isinstance(field_config, dict) and field_config.get("type") == "fixed":
            return "已全选"
        return ""

    def _normalize_scalar(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if text in {"", "---", "/", "N/A"}:
            return None
        return text

    def _extract_numeric_value(self, text: str) -> Optional[int]:
        if not text:
            return None
        hex_match = re.search(r"0x([0-9A-Fa-f]+)", text)
        if hex_match:
            try:
                return int(hex_match.group(1), 16)
            except Exception:
                return None

        prefix_match = re.match(r"\s*(\d+)\s*[:=]", text)
        if prefix_match:
            try:
                return int(prefix_match.group(1))
            except Exception:
                return None

        nums = re.findall(r"\d+", text)
        if nums:
            try:
                return int(nums[0])
            except Exception:
                return None
        return None

    def _normalize_hex(self, value: Any, expected_bytes: Optional[int] = 2) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().replace("0x", "").replace("0X", "").replace(" ", "")
        if not text:
            return None
        try:
            int(text, 16)
        except Exception:
            return None
        if len(text) % 2 == 1:
            text = "0" + text
        if expected_bytes is not None:
            text = text.zfill(expected_bytes * 2)
        return text.upper()

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def _get_service_did(self, service: Optional[Dict[str, Any]]) -> str:
        if not isinstance(service, dict):
            return ""
        request = service.get("request") or {}
        return str(service.get("did") or service.get("serviceId") or request.get("dataIdentifier") or "").strip()

    def _get_service_sid(self, service: Optional[Dict[str, Any]]) -> str:
        if not isinstance(service, dict):
            return ""
        request = service.get("request") or {}
        sid = service.get("service") or request.get("service")
        return str(sid).strip() if sid is not None else ""

    def _get_sub_function(self, service: Optional[Dict[str, Any]]) -> str:
        if not isinstance(service, dict):
            return ""
        request = service.get("request") or {}
        sub_function = service.get("subFunction")
        if sub_function in [None, ""]:
            sub_function = request.get("subFunction")
        return str(sub_function).strip() if sub_function is not None else ""

    def _get_request_source(self, service: Optional[Dict[str, Any]]) -> str:
        if not isinstance(service, dict):
            return ""
        request = service.get("request") or {}
        source = service.get("source") or request.get("source")
        return str(source).strip() if source is not None else ""


    def _should_use_na_fixed_field(self, config: Dict[str, Any], field_name: str) -> bool:
        if field_name != "paramState":
            return False
        if any(config.get(key) for key in ("placeholder", "validation", "value")):
            return False
        if "options" not in config:
            return False
        options = config.get("options")
        return isinstance(options, list) and len(options) == 0

    def _normalize_payload_definition(self, service: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """清洗 payloadDefinition，确保运行期只处理合法结构。"""
        definition = dict((service or {}).get("payloadDefinition") or {})
        definition["mode"] = str(definition.get("mode") or "fixed").strip().lower()
        definition["items"] = [item for item in (definition.get("items") or []) if isinstance(item, dict)]
        definition["stateMappings"] = [item for item in (definition.get("stateMappings") or []) if isinstance(item, dict)]
        return definition

    def _normalize_control_definitions(self, service: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清洗 `$31/$2F` 的控制类型定义，并补齐长度/模式默认值。"""
        definitions = []
        for item in ((service or {}).get("controlDefinitions") or []):
            if not isinstance(item, dict):
                continue
            definitions.append({
                "label": str(item.get("label") or item.get("value") or "").strip(),
                "value": str(item.get("value") or "").strip(),
                "paramByteLength": self._safe_int(item.get("paramByteLength"), self._safe_int((service or {}).get("paramByteLength"), 0)),
                "payloadMode": str(item.get("payloadMode") or "fixed").strip().lower(),
            })
        return definitions

    def _get_selected_control_definition(self, service: Dict[str, Any], selected_control: Optional[str]) -> Optional[Dict[str, Any]]:
        selected = self._normalize_scalar(selected_control)
        definitions = self._normalize_control_definitions(service)
        if not definitions:
            return None
        if selected:
            for item in definitions:
                if selected in {item.get("label"), item.get("value")}:
                    return item
        default_label = ((service.get("routineControlType") or {}).get("default") if isinstance(service.get("routineControlType"), dict) else None)
        for item in definitions:
            if default_label and default_label in {item.get("label"), item.get("value")}:
                return item
        return definitions[0]

    def _get_effective_param_byte_length(self, service: Dict[str, Any], control_definition: Optional[Dict[str, Any]] = None) -> int:
        if isinstance(control_definition, dict) and "paramByteLength" in control_definition:
            return self._safe_int(control_definition.get("paramByteLength"), 0)
        return self._safe_int(service.get("paramByteLength", (service.get("request") or {}).get("paramByteLength")), 0)

    def _get_payload_mode(self, service: Dict[str, Any], control_definition: Optional[Dict[str, Any]] = None) -> str:
        if isinstance(control_definition, dict):
            control_mode = str(control_definition.get("payloadMode") or "").strip().lower()
            if control_mode:
                return control_mode
        definition = self._normalize_payload_definition(service)
        mode = str(definition.get("mode") or "").strip().lower()
        if mode:
            return mode
        source = str(self._get_request_source(service)).strip().lower()
        if source == "ascii":
            return "ascii"
        if source == "fixed":
            return "fixed"
        return "bitfield"

    def _resolve_state_numeric_value(self, service_info: Dict[str, Any], selected_state: Any) -> Optional[int]:
        """把界面里选中的参数状态文本转换为可写入 payload 的数值。

        优先使用 JSON 中的 `stateMappings`，这样“0=关闭 / 1=打开”这类显示文本
        能稳定映射到真实数值；若没有映射，再尝试从文本中提取数字。
        """
        selected_text = self._normalize_scalar(selected_state)
        if not selected_text:
            return None

        state_mappings = (self._normalize_payload_definition(service_info).get("stateMappings") or [])
        for mapping in state_mappings:
            if selected_text in {str(mapping.get("label") or "").strip(), str(mapping.get("value") or "").strip()}:
                if mapping.get("numericValue") is not None:
                    return self._safe_int(mapping.get("numericValue"), 0)
        return self._extract_numeric_value(selected_text)

    def _resolve_target_payload_items(self, service_info: Dict[str, Any], selected_object: Any, payload_definition: Dict[str, Any]) -> List[Dict[str, Any]]:
        """根据表格中选择的参数对象，筛出需要写入的 byte/bit 定义。

        `payloadDefinition.items` 是 Excel 转 JSON 时提前固化的“对象定位表”。
        这里负责把用户当前勾选/选择的对象，映射成真正要写入 payload 的 item 列表。
        """
        items = [item for item in (payload_definition.get("items") or []) if isinstance(item, dict)]
        if not items:
            return []

        selected_objects = self._normalize_selection_list(selected_object)
        if "__ALL__" in selected_objects:
            return [item for item in items if self._normalize_scalar(item.get("object")) not in {None, "---"}]

        if not selected_objects:
            objectless = [item for item in items if self._normalize_scalar(item.get("object")) in {None, "---"}]
            return objectless or items

        matched = []
        for item in items:
            object_name = self._normalize_scalar(item.get("object"))
            if object_name and object_name in selected_objects:
                matched.append(item)
        return matched

    def get_config_path(self, config_type: str) -> str:
        settings = self._system_config_service.load_json(self._config_name, default={}) or {}
        shared_path = settings.get(self._shared_config_key, "")
        if config_type in {"2E", "ROUTINE", "COMMON"}:
            return shared_path or settings.get("last_2e_config_path", "") or settings.get("last_routine_config_path", "")
        return ""

    def save_config_path(self, config_type: str, path: str):
        settings = self._system_config_service.load_json(self._config_name, default={}) or {}
        if config_type in {"2E", "ROUTINE", "COMMON"}:
            settings[self._shared_config_key] = path
        if config_type == "2E":
            settings["last_2e_config_path"] = path
        elif config_type == "ROUTINE":
            settings["last_routine_config_path"] = path
        self._system_config_service.save_json(self._config_name, settings)

    def save_system_config(self, key: str, value: str):
        settings = self._system_config_service.load_json(self._config_name, default={}) or {}
        settings[key] = value
        self._system_config_service.save_json(self._config_name, settings)

    def get_system_config(self, key: str) -> Optional[str]:
        settings = self._system_config_service.load_json(self._config_name, default={})
        return settings.get(key) if settings else None
