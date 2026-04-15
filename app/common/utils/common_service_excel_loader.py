"""常用服务 Excel -> JSON 转换器。

这份模块是整条主链的起点：
1. 识别 Excel 中较个性化的两行表头；
2. 把同一服务的多行定义合并成一条 service；
3. 输出统一 JSON，供“常用 $2E 服务 / 常用 $31&$2F 服务”界面直接加载；
4. 在 JSON 中补齐 `did`、`service`、`paramObject`、`paramState`、
   `payloadDefinition.items[].byte/bit` 等运行期需要的字段。

后续界面和 UDS 指令拼装，都是围绕这里生成的 JSON 结构展开的。
"""

import json
import os
import re
import ast
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

import openpyxl


HEADER_ALIASES = {
    "content": ["content", "内容", "服务内容", "service content", "description", "描述"],
    "service_id": ["serviceid", "服务id", "did", "rid", "dataidentifier", "identifier", "标识符", "did/rid"],
    "request_service": ["request service", "service", "sid", "请求服务", "服务号"],
    "sub_function": ["subfunction", "sub function", "请求子功能", "例程控制类型默认值", "routine default", "默认控制类型"],
    "param_len": ["parambytelength", "byte length", "length", "参数长度", "payload length", "payload长度", "payload 长度"],
    "byte_index": ["byte", "字节", "byte index"],
    "bit_index": ["bit", "位", "bit index"],
    "object_type": ["paramobject type", "参数对象 type", "参数对象 datatype", "参数对象选项 type", "参数对象选项 datatype"],
    "help": ["help", "说明", "帮助", "备注"],
    "help_image": ["helpimage", "图片", "帮助图片", "image", "图片路径"],
    "object_options": ["paramobject list", "参数对象 list", "参数对象选项 list", "对象选项 list"],
    "state_type": ["paramstate type", "参数状态 type", "参数状态 datatype", "参数状态选项 type", "参数状态选项 datatype"],
    "state_options": ["paramstate list", "参数状态 list", "参数状态选项 list", "状态选项 list"],
    "control_options": ["routinecontroltype", "例程控制类型", "控制类型选项", "控制类型", "控制类型 执行操作显示", "control display"],
    "payload_data_type": ["payload生成 datatype", "payload generation datatype", "payload datatype"],
    "object_default": ["paramobject default", "对象默认值", "参数对象默认值"],
    "state_default": ["paramstate default", "状态默认值", "参数状态默认值"],
    "control_default": ["routinecontroltype default", "控制类型默认值", "例程控制类型默认值"],
    "object_placeholder": ["paramobject placeholder", "对象提示", "参数对象提示"],
    "state_placeholder": ["paramstate placeholder", "状态提示", "参数状态提示"],
    "control_placeholder": ["routinecontroltype placeholder", "控制类型提示", "例程控制类型提示"],
    "object_validation": ["paramobject validation", "对象校验", "参数对象校验"],
    "state_validation": ["paramstate validation", "状态校验", "参数状态校验"],
    "control_validation": ["routinecontroltype validation", "控制类型校验", "例程控制类型校验"],
    "request_source": ["source", "数据来源", "request source"],
    "raw_request": ["rawrequest", "raw request", "原始请求", "手工报文", "自定义报文", "直发请求"],
    "calculation_type": ["calculationtype", "转换类型", "计算类型"],
}


def convert_common_service_excel(input_path: str, output_dir: str, output_filename: str = "common_service_config.json") -> str:
    """把 Excel 直接转换为统一 JSON 文件，并返回输出路径。"""
    data = parse_common_service_excel(input_path)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return output_path


# noinspection PyUnreachableCode
def parse_common_service_excel(file_path: str) -> Dict[str, Any]:
    """解析 Excel，产出界面/服务层统一使用的 JSON 根结构。

    输出核心分成两桶：
    - `services2E`: 常用 `$2E` 服务
    - `services31_2F`: 常用 `$31/$2F` 服务

    每条服务都会被整理成同一套 schema，后续界面只需要按字段渲染，
    服务执行层只需要按 `payloadDefinition` 计算 payload。
    """
    workbook = cast(Any, openpyxl.load_workbook(file_path, data_only=True))
    result = {
        "meta": {
            "generator": "common_service_excel_loader",
            "sourceFile": os.path.basename(file_path),
            "version": "1.0",
        },
        "services2E": [],
        "services31_2F": [],
        "systemConfig": {
            "requireExtendedSessionAndSecurity": True,
            "lastReadTimeUpdateService": "0x2E",
        },
    }

    for worksheet in workbook.worksheets:
        _parse_sheet(worksheet, result)

    _reindex_services(result["services2E"])
    _reindex_services(result["services31_2F"])
    return result


def _parse_sheet(worksheet, result: Dict[str, Any]):
    """解析单个工作表，并把行数据持续合并成 service 定义。

    Excel 的常见形态是：
    - 前几行里有 1~2 行表头；
    - 一个服务可能横跨多行；
    - 第一行给出内容/DID/SID，后续行继续补充对象、状态、byte/bit。

    因此这里的关键逻辑是：
    - 先识别表头与副表头；
    - 再判断“当前行是否开启一个新服务”；
    - 如果不是新服务，就把这一行 merge 到当前服务里。
    """
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return

    header_index = _find_header_row(rows)
    secondary_header_index = _find_secondary_header_row(rows, header_index)
    headers = _build_combined_headers(
        rows[header_index],
        rows[secondary_header_index] if secondary_header_index is not None else None,
    )
    column_map = _build_column_map(headers)
    if not column_map:
        return

    current_service: Optional[Dict[str, Any]] = None
    current_bucket: Optional[List[Dict[str, Any]]] = None

    data_start_index = (secondary_header_index + 1) if secondary_header_index is not None else (header_index + 1)
    for row in rows[data_start_index:]:
        if _is_empty_row(row):
            continue

        row_data = _read_row_values(row, column_map)
        starts_new_service = any(row_data.get(key) for key in ("content", "service_id", "request_service"))

        if starts_new_service:
            # 命中“新服务起始行”时，先创建 service 骨架；后面的连续行再不断补充该 service。
            current_service = _build_service_definition(worksheet.title, row_data)
            if current_service is None:
                continue
            current_bucket = result["services2E"] if _service_family(current_service) == "2E" else result["services31_2F"]
            current_bucket.append(current_service)
        elif current_service is None:
            continue

        if current_service is None:
            continue

        _merge_service_row(current_service, row_data)

    for bucket in (result["services2E"], result["services31_2F"]):
        for service in bucket:
            _finalize_service(service)


def _find_header_row(rows: List[Tuple[Any, ...]], max_scan: int = 12) -> int:
    best_index = 0
    best_score = -1
    for index, row in enumerate(rows[:max_scan]):
        secondary_row = rows[index + 1] if index + 1 < len(rows) else None
        score = _score_header_block(row, secondary_row)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def _find_secondary_header_row(rows: List[Tuple[Any, ...]], header_index: int) -> Optional[int]:
    candidate_index = header_index + 1
    if candidate_index >= len(rows):
        return None

    candidate_row = rows[candidate_index]
    normalized_cells = [_normalize_header(value) for value in candidate_row]
    has_detail_keywords = any(
        keyword in cell
        for cell in normalized_cells
        for keyword in ("list", "default", "placeholder", "validation", "选项", "默认", "提示", "校验")
    )
    return candidate_index if _header_row_score(candidate_row) > 0 or has_detail_keywords else None


def _score_header_block(primary_row: Tuple[Any, ...], secondary_row: Optional[Tuple[Any, ...]] = None) -> int:
    score = _header_row_score(primary_row)
    if secondary_row is not None:
        score += _header_row_score(secondary_row)
        score += _header_match_score(_build_combined_headers(primary_row, secondary_row)) * 2
    return score


def _header_row_score(row: Tuple[Any, ...]) -> int:
    return _header_match_score([_normalize_header(value) for value in row])


def _header_match_score(headers: List[str]) -> int:
    score = 0
    for aliases in HEADER_ALIASES.values():
        if any(alias in cell for cell in headers for alias in aliases):
            score += 1
    return score


def _build_combined_headers(primary_row: Tuple[Any, ...], secondary_row: Optional[Tuple[Any, ...]] = None) -> List[str]:
    max_len = max(len(primary_row), len(secondary_row) if secondary_row else 0)
    headers: List[str] = []
    last_primary = ""
    for index in range(max_len):
        primary = _normalize_header(primary_row[index] if index < len(primary_row) else "")
        secondary = _normalize_header(secondary_row[index] if secondary_row and index < len(secondary_row) else "")
        effective_primary = primary or (last_primary if secondary else "")
        if not primary:
            headers.append(f"{effective_primary} {secondary}".strip() if effective_primary and secondary else secondary)
        elif not secondary or effective_primary == secondary:
            headers.append(effective_primary)
        else:
            headers.append(f"{effective_primary} {secondary}".strip())
        if primary:
            last_primary = primary
    return headers


def _build_column_map(headers: List[str]) -> Dict[str, int]:
    column_map: Dict[str, int] = {}
    for field_name, aliases in HEADER_ALIASES.items():
        for index, header in enumerate(headers):
            if _match_header_field(field_name, header):
                column_map[field_name] = index
                break
    return column_map


def _read_row_values(row: Tuple[Any, ...], column_map: Dict[str, int]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for field_name, index in column_map.items():
        values[field_name] = _clean_text(row[index] if index < len(row) else "")
    return values


def _build_service_definition(sheet_name: str, row_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """把 Excel 中“某个服务的首行”转换成统一 service 字典。

    这里会完成几件关键事情：
    - 从表头内容抽取 `did` / `service` / `subFunction`
    - 构造 `paramObject` / `paramState` 字段配置
    - 构造 `payloadDefinition`，把 byte/bit 映射提前固化进 JSON
    - 对 `$31/$2F` 额外生成 `routineControlType` / `controlDefinitions`

    这一步决定了后续界面如何生成下拉框，以及执行时如何计算 payload。
    """
    content = row_data.get("content") or ""
    service_id = row_data.get("service_id") or _extract_hex_id(content)
    request_service = _normalize_sid(row_data.get("request_service") or _infer_request_service(sheet_name, content))
    if not service_id or not request_service:
        return None

    param_object = _build_field_definition(
        field_type_text=row_data.get("object_type", ""),
        options_text=row_data.get("object_options", ""),
        default=row_data.get("object_default", ""),
        placeholder=row_data.get("object_placeholder", ""),
        validation=row_data.get("object_validation", ""),
        fallback_value="N/A",
        field_name="paramObject",
    )
    param_state = _build_field_definition(
        field_type_text=row_data.get("state_type", ""),
        options_text=row_data.get("state_options", ""),
        default=row_data.get("state_default", ""),
        placeholder=row_data.get("state_placeholder", ""),
        validation=row_data.get("state_validation", ""),
        fallback_value="N/A",
        field_name="paramState",
    )

    param_byte_length = _safe_int(row_data.get("param_len"), 0)
    sub_function = row_data.get("sub_function") or ("00" if request_service == "0x2E" else "0x01" if request_service == "0x31" else "0x00")
    # `source` 现在不再作为普通服务的必存字段，而是尽量运行期推导；
    # 只有“手工原始报文直发”这类特殊场景，才在 JSON 中显式保留 `source: manual`。
    request_source = row_data.get("request_source") or _infer_request_source(param_byte_length, param_object, param_state, row_data.get("payload_data_type", ""))
    raw_request = _should_mark_row_as_raw_request(
        row_data,
        request_service=request_service,
        service_id=service_id,
        param_byte_length=param_byte_length,
        param_object=param_object,
        param_state=param_state,
    )
    if raw_request:
        # 自定义 `$2E` 原始请求不能再按“2E + DID + payload”去计算，
        # 因此这里显式写出 `rawRequest/manual`，让运行期直接走“整包直发”。
        request_source = "manual"

    service = {
        "content": content or f"{request_service} 服务({_normalize_hex_id(service_id)})",
        "did": _normalize_hex_id(service_id),
        "service": request_service,
        "subFunction": sub_function,
        "paramByteLength": param_byte_length,
        "help": row_data.get("help", ""),
        "helpImage": row_data.get("help_image", ""),
        "paramObject": param_object,
        "paramState": param_state,
        "payloadDefinition": _build_payload_definition(row_data, param_byte_length, request_source),
    }
    if raw_request:
        service["rawRequest"] = True
        service["source"] = "manual"

    if request_service in {"0x31", "0x2F"}:
        service["routineControlType"] = _build_field_definition(
            field_type_text="enum",
            options_text=row_data.get("control_options", ""),
            default=row_data.get("control_options", ""),
            placeholder=row_data.get("control_placeholder", ""),
            validation=row_data.get("control_validation", ""),
            fallback_value=row_data.get("sub_function") or "N/A",
            field_name="routineControlType",
        )
        service["controlDefinitions"] = _build_control_definitions(row_data, request_source)

    return service


def _merge_service_metadata(service: Dict[str, Any], row_data: Dict[str, str]):
    if row_data.get("help") and not service.get("help"):
        service["help"] = row_data["help"]
    if row_data.get("help_image") and not service.get("helpImage"):
        service["helpImage"] = row_data["help_image"]


def _merge_service_row(service: Dict[str, Any], row_data: Dict[str, str]):
    """把当前 Excel 行追加合并到已经创建好的 service 中。

    Excel 一个服务经常拆成多行：
    - 某几行补参数对象选项；
    - 某几行补参数状态选项；
    - 某几行补不同对象对应的 byte/bit。

    所以这里不会新建 service，而是把字段定义、控制类型定义、
    payloadDefinition.items/stateMappings 逐步汇总到同一条 service 上。
    """
    _merge_service_metadata(service, row_data)

    _merge_field_definition(
        service,
        "paramObject",
        _build_field_definition(
            field_type_text=row_data.get("object_type", ""),
            options_text=row_data.get("object_options", ""),
            default=row_data.get("object_default", ""),
            placeholder=row_data.get("object_placeholder", ""),
            validation=row_data.get("object_validation", ""),
            fallback_value="N/A",
            field_name="paramObject",
        ),
    )
    _merge_field_definition(
        service,
        "paramState",
        _build_field_definition(
            field_type_text=row_data.get("state_type", ""),
            options_text=row_data.get("state_options", ""),
            default=row_data.get("state_default", ""),
            placeholder=row_data.get("state_placeholder", ""),
            validation=row_data.get("state_validation", ""),
            fallback_value="N/A",
            field_name="paramState",
        ),
    )

    if service.get("service") in {"0x31", "0x2F"}:
        _merge_field_definition(
            service,
            "routineControlType",
            _build_field_definition(
                field_type_text="enum",
                options_text=row_data.get("control_options", ""),
                default=row_data.get("control_options", ""),
                placeholder=row_data.get("control_placeholder", ""),
                validation=row_data.get("control_validation", ""),
                fallback_value=row_data.get("sub_function") or "N/A",
                field_name="routineControlType",
            ),
        )
        _merge_control_definitions(service, row_data)

    _merge_payload_definition(service, row_data)

    raw_request = _should_mark_row_as_raw_request(
        row_data,
        request_service=_normalize_sid(service.get("service")),
        service_id=service.get("did"),
        param_byte_length=_safe_int(service.get("paramByteLength"), 0),
        param_object=service.get("paramObject") if isinstance(service.get("paramObject"), dict) else {},
        param_state=service.get("paramState") if isinstance(service.get("paramState"), dict) else {},
    )
    if raw_request:
        # 一个服务可能分散在多行里；即使首行没有足够信息识别 raw/manual，
        # merge 阶段也要继续补标记，避免最终 JSON 退回到推断式行为。
        service["rawRequest"] = True
        service["source"] = "manual"


def _build_field_definition(field_type_text: str, options_text: str, default: str, placeholder: str, validation: str, fallback_value: str, field_name: str) -> Dict[str, Any]:
    """把 Excel 列内容标准化为界面字段配置。

    输出形态最终会被界面解释为：
    - `options` -> 下拉/复选下拉
    - `placeholder` / `validation` -> 输入框
    - `value` -> 固定只读值
    """
    options = _extract_options(options_text, field_name)
    normalized_field_type = _normalize_field_type_text(field_type_text)
    field: Dict[str, Any] = {}
    if options:
        field["options"] = options
        field["default"] = default or _default_option_value(field_name, options)
        return _collapse_empty_field_definition(field_name, field, fallback_value=fallback_value)
    if normalized_field_type in {"input", "ascii", "string", "ip", "port", "manual"}:
        if placeholder:
            field["placeholder"] = placeholder
        validation_value = validation or _normalize_validation(field_type_text)
        if validation_value:
            field["validation"] = validation_value
        return _collapse_empty_field_definition(field_name, field, fallback_value=fallback_value)
    if placeholder or validation:
        if placeholder:
            field["placeholder"] = placeholder
        if validation:
            field["validation"] = validation
        return _collapse_empty_field_definition(field_name, field, fallback_value=fallback_value)
    field["value"] = fallback_value
    return _collapse_empty_field_definition(field_name, field, fallback_value=fallback_value)


def _merge_field_definition(service: Dict[str, Any], field_name: str, incoming: Dict[str, Any]):
    current = service.get(field_name)
    if not isinstance(current, dict):
        service[field_name] = _collapse_empty_field_definition(field_name, incoming, service)
        return

    current_options = current.get("options") or []
    incoming_options = incoming.get("options") or []
    if incoming_options:
        merged_options = _dedupe_options([*current_options, *incoming_options])
        service[field_name] = _collapse_empty_field_definition(field_name, {
            "options": merged_options,
            "default": current.get("default") or incoming.get("default") or _default_option_value(field_name, merged_options),
        }, service)
        return

    if current_options:
        return

    if current.get("placeholder") or current.get("validation"):
        return

    if incoming.get("placeholder") or incoming.get("validation"):
        service[field_name] = _collapse_empty_field_definition(field_name, incoming, service)
        return

    if incoming.get("value") not in {None, "", "N/A"} or not current.get("value"):
        service[field_name] = _collapse_empty_field_definition(field_name, incoming, service)


def _build_payload_definition(row_data: Dict[str, str], param_byte_length: int, request_source: str) -> Dict[str, Any]:
    """构造运行期 payload 定义。

    这是 Excel -> JSON 链路里最重要的运行时桥梁：
    - `mode` 描述 payload 采用 fixed / ascii / bitfield / identity 哪种生成方式；
    - `stateMappings` 把“参数状态下拉文本”映射成真正数值；
    - `items` 记录“参数对象 -> byte/bit”的定位关系。

    后续用户在表格里选对象、选状态时，服务层就是读取这里来计算 UDS payload。
    """
    mode = _infer_payload_mode(row_data, request_source, param_byte_length)
    definition: Dict[str, Any] = {
        "mode": mode,
        "stateMappings": _build_state_mappings(row_data.get("state_options", "")),
        "items": [],
    }
    item = _build_payload_item(row_data, mode, param_byte_length)
    if item:
        definition["items"] = [item]
    return definition


def _merge_payload_definition(service: Dict[str, Any], row_data: Dict[str, str]):
    definition = service.setdefault("payloadDefinition", {"mode": "fixed", "stateMappings": [], "items": []})
    if not isinstance(definition, dict):
        definition = {"mode": "fixed", "stateMappings": [], "items": []}
        service["payloadDefinition"] = definition

    param_byte_length = _safe_int(service.get("paramByteLength"), 0)
    request_source = str(service.get("source", "")).strip()
    row_mode = _infer_payload_mode(row_data, request_source, param_byte_length)
    if definition.get("mode") in {None, "", "fixed"} and row_mode not in {None, "", "fixed"}:
        definition["mode"] = row_mode

    definition["stateMappings"] = _merge_mapping_lists(
        definition.get("stateMappings") or [],
        _build_state_mappings(row_data.get("state_options", "")),
        keys=("label", "value", "numericValue"),
    )

    item = _build_payload_item(row_data, row_mode, param_byte_length)
    if item:
        definition["items"] = _merge_mapping_lists(definition.get("items") or [], [item], keys=("object", "byte", "bit"))


def _build_control_definitions(row_data: Dict[str, str], request_source: str) -> List[Dict[str, Any]]:
    definition = _build_control_definition(row_data, request_source)
    return [definition] if definition else []


def _merge_control_definitions(service: Dict[str, Any], row_data: Dict[str, str]):
    incoming = _build_control_definitions(row_data, str(service.get("source", "")).strip())
    if not incoming:
        return
    service["controlDefinitions"] = _merge_mapping_lists(
        service.get("controlDefinitions") or [],
        incoming,
        keys=("label", "value", "paramByteLength", "payloadMode"),
    )


def _build_control_definition(row_data: Dict[str, str], request_source: str) -> Optional[Dict[str, Any]]:
    """为 `$31/$2F` 的单个控制类型构造定义。

    例程控制类型不仅决定 control byte，也可能决定：
    - 当前 payload 的长度；
    - 当前 payload 的生成模式。

    因此这里会把控制显示文本、实际值、payload 规则一起写入 JSON。
    """
    label = _clean_text(row_data.get("control_options", ""))
    value = _normalize_control_value(row_data.get("sub_function", ""))
    if not label and not value:
        return None

    param_byte_length = _safe_int(row_data.get("param_len"), 0)
    payload_mode = _infer_payload_mode(row_data, request_source, param_byte_length)
    return {
        "label": label or value,
        "value": value or "00",
        "paramByteLength": param_byte_length,
        "payloadMode": payload_mode,
    }


def _build_payload_item(row_data: Dict[str, str], mode: str, param_byte_length: int) -> Optional[Dict[str, Any]]:
    """从一行 Excel 中抽取一条“对象 -> byte/bit”映射。"""
    object_label = _clean_option_label(row_data.get("object_options", ""))
    byte_value = _parse_byte_value(row_data.get("byte_index", ""), mode, param_byte_length)
    bit_value = _parse_bit_value(row_data.get("bit_index", ""), mode)

    if object_label in {"", "---"} and byte_value is None and bit_value is None:
        return None

    item: Dict[str, Any] = {
        "object": object_label or "---",
        "byte": 0 if byte_value is None and mode in {"identity", "ascii"} and param_byte_length > 0 else byte_value,
        "bit": "All" if bit_value is None and mode in {"identity", "ascii"} and param_byte_length > 0 else bit_value,
    }
    return item


def _build_state_mappings(options_text: str) -> List[Dict[str, Any]]:
    mappings: List[Dict[str, Any]] = []
    for option in _extract_options(options_text, "paramState"):
        if option in {"/", "---", "N/A"}:
            continue
        numeric_value = _extract_numeric_value(option)
        entry: Dict[str, Any] = {
            "label": option,
            "value": _extract_state_raw_value(option),
        }
        if numeric_value is not None:
            entry["numericValue"] = numeric_value
        mappings.append(entry)
    return mappings


def _merge_mapping_lists(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for entry in [*(existing or []), *(incoming or [])]:
        if not isinstance(entry, dict):
            continue
        signature = tuple(entry.get(key) for key in keys)
        if signature in seen:
            continue
        seen.add(signature)
        result.append(entry)
    return result


def _finalize_service(service: Dict[str, Any]):
    family = _service_family(service)

    for field_name in ("paramObject", "paramState", "routineControlType"):
        if field_name in service and isinstance(service.get(field_name), dict):
            service[field_name] = _collapse_empty_field_definition(field_name, service[field_name], service)

    if family == "2E":
        service.pop("routineControlType", None)

    if _should_mark_service_as_raw_request(service):
        # 最终兜底：把整条 service 汇总后的信息再检查一次。
        # 这样即使 Excel 某些列落在后续行里，也能稳定产出 raw/manual。
        service["rawRequest"] = True
        service["source"] = "manual"
        payload_definition = service.get("payloadDefinition")
        if isinstance(payload_definition, dict) and not payload_definition.get("items"):
            payload_definition["mode"] = "fixed"
    else:
        # 普通服务的 `source` 已经可以从 payloadDefinition / field config 推导，
        # 不再需要在 JSON 中重复保存，避免 schema 冗余与双重语义源。
        service.pop("source", None)

    # `calculationType` 仅是旧版本的描述性元数据，不参与界面渲染和执行计算，
    # 这里统一清理，保证新 JSON 只保留真正会被运行期消费的字段。
    service.pop("calculationType", None)


def _should_mark_row_as_raw_request(
    row_data: Dict[str, str],
    *,
    request_service: str,
    service_id: Any,
    param_byte_length: int,
    param_object: Dict[str, Any],
    param_state: Dict[str, Any],
) -> bool:
    # 行级识别：优先信任 Excel 的显式标记；
    # 若 Excel 未显式给出，再用“自定义2E + 缺 DID + 输入型 + 无枚举项”兜底判断。
    explicit_flag = str(row_data.get("raw_request") or "").strip().lower()
    if explicit_flag in {"1", "true", "yes", "y", "raw", "manual"}:
        return True

    source_text = str(row_data.get("request_source") or "").strip().lower()
    if source_text in {"manual", "raw", "direct", "full_request"}:
        return True

    content = str(row_data.get("content") or "").strip().lower()
    normalized_did = str(service_id or "").strip().lower()
    validation = str((param_object or {}).get("validation") or "").strip().lower()
    param_object_has_input = _has_input_config(param_object)
    param_state_has_input = _has_input_config(param_state)
    object_options = (param_object or {}).get("options") or []
    state_options = (param_state or {}).get("options") or []
    missing_did = normalized_did in {"", "/", "---", "n/a"}
    custom_content = content in {"自定义2e请求", "自定义 2e 请求"} or ("自定义2e" in content)
    input_like = validation in {"string", "raw", "hex", "uds", "manual"} or param_object_has_input or param_state_has_input
    no_enum_options = not object_options and not state_options

    return (
        _normalize_sid(request_service) == "0x2E"
        and missing_did
        and param_byte_length <= 0
        and no_enum_options
        and (custom_content or input_like)
    )


def _should_mark_service_as_raw_request(service: Dict[str, Any]) -> bool:
    # service 级识别：基于 merge 后的完整字段再做一次判断，
    # 保证最终 JSON 输出稳定，不依赖某一行是否恰好提供了全部信息。
    explicit_flag = bool(service.get("rawRequest"))
    if explicit_flag:
        return True

    source_text = str(service.get("source") or "").strip().lower()
    if source_text in {"manual", "raw", "direct", "full_request"}:
        return True

    content = str(service.get("content") or "").strip().lower()
    sid = _normalize_sid(service.get("service"))
    did_text = str(service.get("did") or "").strip().lower()
    param_byte_length = _safe_int(service.get("paramByteLength"), 0)
    param_object = service.get("paramObject") if isinstance(service.get("paramObject"), dict) else {}
    param_state = service.get("paramState") if isinstance(service.get("paramState"), dict) else {}
    validation = str(param_object.get("validation") or "").strip().lower()
    missing_did = did_text in {"", "/", "---", "n/a"}
    no_enum_options = not (param_object.get("options") or []) and not (param_state.get("options") or [])
    custom_content = content in {"自定义2e请求", "自定义 2e 请求"} or ("自定义2e" in content)
    input_like = validation in {"string", "raw", "hex", "uds", "manual"} or _has_input_config(param_object) or _has_input_config(param_state)

    return sid == "0x2E" and missing_did and param_byte_length <= 0 and no_enum_options and (custom_content or input_like)


def _collapse_empty_field_definition(field_name: str, field: Dict[str, Any], service: Optional[Dict[str, Any]] = None, fallback_value: str = "N/A") -> Dict[str, Any]:
    if not isinstance(field, dict):
        return field

    options = field.get("options")
    if isinstance(options, list):
        cleaned_options = _dedupe_options(options)
        if cleaned_options:
            collapsed = dict(field)
            collapsed["options"] = cleaned_options
            if field_name == "routineControlType":
                collapsed["default"] = collapsed.get("default") or cleaned_options[0]
            else:
                collapsed["default"] = collapsed.get("default") or "---"
            return collapsed

        if not any(field.get(key) for key in ("placeholder", "validation", "value")):
            if field_name == "routineControlType":
                routine_value = _clean_text((service or {}).get("subFunction")) or fallback_value
                return {"value": routine_value}
            return {"value": fallback_value}

    return field


def _reindex_services(services: List[Dict[str, Any]]):
    for index, service in enumerate(services, start=1):
        service["index"] = index


def _service_family(service: Dict[str, Any]) -> str:
    sid = _normalize_sid(service.get("service") or (service.get("request") or {}).get("service"))
    if sid == "0x31":
        return "31"
    if sid == "0x2F":
        return "2F"
    return "2E"


def _match_header_field(field_name: str, header: str) -> bool:
    normalized_header = _normalize_header(header)
    compact_header = normalized_header.replace(" ", "")
    header_candidates = {normalized_header, compact_header}

    if field_name == "object_type":
        return _header_has_any(header_candidates, ["参数对象", "参数对象选项", "paramobject"]) and _header_has_any(header_candidates, ["type", "datatype"])
    if field_name == "object_options":
        return _header_has_any(header_candidates, ["参数对象", "参数对象选项", "paramobject"]) and _header_has_any(header_candidates, ["list", "列表"])
    if field_name == "state_type":
        return _header_has_any(header_candidates, ["参数状态", "参数状态选项", "paramstate"]) and _header_has_any(header_candidates, ["type", "datatype"])
    if field_name == "state_options":
        return _header_has_any(header_candidates, ["参数状态", "参数状态选项", "paramstate"]) and _header_has_any(header_candidates, ["list", "列表"])
    if field_name == "control_options":
        return _header_has_any(header_candidates, ["控制类型", "例程控制类型", "routinecontroltype"]) and _header_has_any(header_candidates, ["执行操作显示", "display", "show"])
    if field_name == "sub_function":
        if _header_has_any(header_candidates, ["控制类型", "例程控制类型", "routinecontroltype"]):
            return _header_has_any(header_candidates, ["control", "子功能", "subfunction", "默认控制类型"])
    if field_name == "payload_data_type":
        return _header_has_any(header_candidates, ["payload生成", "payloadgeneration", "payload"]) and _header_has_any(header_candidates, ["datatype", "data type"])
    if field_name == "byte_index":
        return _header_has_any(header_candidates, ["byte", "字节"])
    if field_name == "bit_index":
        return _header_has_any(header_candidates, ["bit", "位"])

    aliases = HEADER_ALIASES.get(field_name, [])
    return any(alias in candidate for candidate in header_candidates for alias in aliases)


def _header_has_any(header_candidates: Iterable[str], keywords: Iterable[str]) -> bool:
    return any(keyword in candidate for candidate in header_candidates for keyword in keywords)


def _infer_request_service(sheet_name: str, content: str) -> str:
    joined = f"{sheet_name} {content}".upper()
    if "$2F" in joined or " 2F" in joined:
        return "0x2F"
    if "$31" in joined or " 31" in joined:
        return "0x31"
    return "0x2E"


def _normalize_sid(value: Any) -> str:
    text = _clean_text(value).upper().replace(" ", "")
    if not text:
        return ""
    if not text.startswith("0X"):
        text = f"0x{text}"
    return text.replace("0X", "0x")


def _normalize_hex_id(value: Any) -> str:
    text = _clean_text(value).upper().replace(" ", "")
    if not text:
        return ""
    while text.startswith("0X0X"):
        text = text[2:]
    if text.startswith("0X"):
        return text.replace("0X", "0x")
    if re.fullmatch(r"[0-9A-F]+", text):
        return f"0x{text}"
    return text


def _extract_hex_id(text: str) -> str:
    match = re.search(r"0x[0-9A-Fa-f]+", text or "")
    return match.group(0) if match else ""


def _split_options(value: Any) -> List[str]:
    text = _clean_text(value)
    if not text:
        return []
    parts = re.split(r"[\n;,；，|]+", text)
    options: List[str] = []
    for part in parts:
        cleaned = _clean_text(part)
        if cleaned and cleaned not in options:
            options.append(cleaned)
    return options


def _extract_options(value: Any, field_name: str = "") -> List[str]:
    """从 Excel 单元格中提取选项列表。

    兼容两类输入：
    - 普通分隔文本：`CCU, 其它节点`
    - 结构化文本 / List 字典：`{"List": [...]}`

    `paramObject`、`paramState` 都会从这里把 Excel 的 List 转成界面 options。
    """
    text = _clean_text(value)
    if not text:
        return []

    structured = _extract_list_from_structured_text(text, field_name)
    if structured:
        return structured

    return _split_options(text)


def _extract_list_from_structured_text(text: str, field_name: str = "") -> List[str]:
    """优先从结构化文本里的 `List` 节点提取选项。

    这段逻辑专门应对 VCC Excel 中那种“单元格里嵌套字典/列表”的写法，
    也是 `paramObject.options`、`paramState.options` 能准确落到 JSON 的关键。
    """
    parsed = _try_parse_structured_options(text, field_name)
    if parsed:
        return parsed

    normalized = text.replace("：", ":")
    match = re.search(r"(?is)\blist\b\s*[:=]\s*(.+)", normalized)
    if not match:
        return []

    raw_list = match.group(1).strip()
    if raw_list.startswith("["):
        closing = raw_list.rfind("]")
        if closing != -1:
            raw_list = raw_list[1:closing]

    raw_lines = []
    for line in raw_list.splitlines():
        stripped = line.strip().strip(",")
        if not stripped:
            continue
        if re.match(r"^[A-Za-z_\u4e00-\u9fff\s]+\s*[:=]", stripped):
            break
        raw_lines.append(stripped.lstrip("-*•·0123456789. ").strip())

    if raw_lines:
        return _dedupe_options(raw_lines)

    return _split_options(raw_list)


def _try_parse_structured_options(text: str, field_name: str = "") -> List[str]:
    candidates = [text]
    if "'" in text and '"' not in text:
        candidates.append(text.replace("'", '"'))

    for candidate in candidates:
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(candidate)
            except Exception:
                continue
            extracted = _extract_list_value(parsed, field_name)
            if extracted:
                return extracted
    return []


def _extract_list_value(value: Any, field_name: str = "") -> List[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() == "list":
                return _extract_list_value(item, field_name)
        for item in value.values():
            extracted = _extract_list_value(item, field_name)
            if extracted:
                return extracted
        return []

    if isinstance(value, (list, tuple, set)):
        options: List[str] = []
        for item in value:
            if isinstance(item, dict):
                text = _format_structured_option_item(item, field_name)
                if text:
                    options.append(text)
                    continue
            text = _clean_text(item)
            if text:
                options.append(text)
        return _dedupe_options(options)

    return []


def _dedupe_options(options: Iterable[str]) -> List[str]:
    result: List[str] = []
    for option in options:
        cleaned = _clean_text(option)
        if cleaned in {"/", "---", "N/A", "NA", "NONE", "None"}:
            continue
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _format_structured_option_item(item: Dict[str, Any], field_name: str) -> str:
    if field_name == "paramState":
        state_text = _format_state_option_item(item)
        if state_text:
            return state_text

    display_text = _pick_first_text(
        item,
        [
            "shortName",
            "shortDisplay",
            "alias",
            "abbr",
            "简称",
            "短名称",
            "短名",
            "displayName",
            "display",
            "显示名称",
            "显示名",
            "caption",
            "title",
            "label",
            "名称",
            "caption",
            "name",
            "namezh",
            "namecn",
            "text",
            "desc",
            "description",
            "描述",
            "value",
        ],
    )
    if display_text:
        return display_text

    return ""


def _format_state_option_item(item: Dict[str, Any]) -> str:
    code_text = _pick_first_text(
        item,
        [
            "value",
            "optionValue",
            "key",
            "code",
            "enumValue",
            "stateValue",
            "id",
            "index",
            "data",
            "值",
            "编码",
        ],
    )
    label_text = _pick_first_text(
        item,
        [
            "shortName",
            "shortDisplay",
            "displayName",
            "display",
            "alias",
            "label",
            "显示名称",
            "显示名",
            "名称",
            "name",
            "text",
            "desc",
            "description",
            "描述",
        ],
    )

    if code_text and label_text and code_text != label_text:
        return f"{code_text}={label_text}"

    return label_text or code_text


def _pick_first_text(item: Dict[str, Any], keys: List[str]) -> str:
    normalized = {str(key).strip().lower(): value for key, value in item.items()}
    for key in keys:
        text = _clean_text(normalized.get(key.lower()))
        if text:
            return text

    suffix_aliases = {
        "shortname": ["简称", "短名称", "短名"],
        "shortdisplay": ["短显示", "短显示名"],
        "alias": ["别名"],
        "abbr": ["缩写"],
        "displayname": ["显示名称", "显示名"],
        "display": ["显示"],
        "label": ["标签"],
        "name": ["名称"],
        "text": ["文本"],
        "desc": ["描述"],
        "description": ["说明"],
        "value": ["值", "编码"],
    }
    suffix_groups = list(suffix_aliases.keys())
    for suffix in suffix_groups:
        localized_suffixes = suffix_aliases.get(suffix, [])
        for key, value in normalized.items():
            compact_key = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", key)
            if compact_key.endswith(suffix) or any(compact_key.endswith(localized) for localized in localized_suffixes):
                text = _clean_text(value)
                if text:
                    return text

    for value in normalized.values():
        if isinstance(value, (dict, list, tuple, set)):
            continue
        text = _clean_text(value)
        if text:
            return text
    return ""


def _default_option_value(field_name: str, options: List[str]) -> str:
    if field_name == "routineControlType":
        return options[0] if options else "N/A"
    return "---"


def _infer_request_source(param_byte_length: int, param_object: Dict[str, Any], param_state: Dict[str, Any], payload_data_type: str = "") -> str:
    # 这里只负责“普通服务”的推导来源：
    # - 输入型 -> ascii
    # - 零长度 -> fixed
    # - 其余默认按 calculated 处理
    # `manual/raw` 场景由 rawRequest 识别逻辑单独接管。
    if _has_input_config(param_object) or _has_input_config(param_state):
        return "ascii"
    if _normalize_field_type_text(payload_data_type) == "ascii":
        return "ascii"
    if _safe_int(param_byte_length, 0) <= 0:
        return "fixed"
    return "calculated"


def _infer_calculation_type(request_source: str) -> str:
    return "JSON" if str(request_source).strip().lower() == "calculated" else "N/A"


def _infer_payload_mode(row_data: Dict[str, str], request_source: str, param_byte_length: int) -> str:
    payload_type = _normalize_field_type_text(row_data.get("payload_data_type", ""))
    if request_source.strip().lower() == "ascii" or payload_type == "ascii":
        return "ascii"
    if payload_type in {"enum"}:
        byte_value = _parse_byte_value(row_data.get("byte_index", ""), "bitfield", param_byte_length)
        bit_value = _parse_bit_value(row_data.get("bit_index", ""), "bitfield")
        if byte_value is not None and isinstance(bit_value, int):
            return "bitfield"
    if payload_type == "identity":
        return "identity"
    if param_byte_length <= 0:
        return "fixed"
    if payload_type == "enum":
        return "identity"
    return "fixed"


def _has_input_config(field: Dict[str, Any]) -> bool:
    return isinstance(field, dict) and any(field.get(key) for key in ("placeholder", "validation")) and not field.get("options")


def _normalize_field_type_text(value: Any) -> str:
    text = _clean_text(value).lower().replace("_", " ")
    if not text or text in {"/", "n/a", "na", "none"}:
        return "fixed"
    if "ascii" in text:
        return "ascii"
    if "string" in text:
        return "string"
    if "enum" in text:
        return "enum"
    if text in {"ip", "port", "input", "manual"}:
        return text
    if "identity" in text or "boolean" in text:
        return "enum"
    return text


def _normalize_validation(value: Any) -> str:
    field_type = _normalize_field_type_text(value)
    if field_type in {"ip", "port", "string"}:
        return field_type
    return ""


def _normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean_text(value).lower())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_option_label(value: Any) -> str:
    text = _clean_text(value)
    if text in {"", "/", "---", "N/A"}:
        return ""
    return text


def _parse_byte_value(value: Any, mode: str, param_byte_length: int) -> Optional[int]:
    text = _clean_text(value)
    if not text or text in {"/", "---", "N/A"}:
        return 0 if mode in {"identity", "ascii"} and param_byte_length > 0 else None
    if text.lower() == "all":
        return 0
    try:
        return int(text)
    except Exception:
        return None


def _parse_bit_value(value: Any, mode: str) -> Any:
    text = _clean_text(value)
    if not text or text in {"/", "---", "N/A"}:
        return "All" if mode in {"identity", "ascii"} else None
    if text.lower() == "all":
        return "All"
    try:
        return int(text)
    except Exception:
        return text


def _normalize_control_value(value: Any) -> str:
    text = _clean_text(value)
    if not text or text in {"/", "---", "N/A"}:
        return ""
    if re.search(r"0x[0-9A-Fa-f]+", text):
        return _normalize_sid(re.search(r"0x[0-9A-Fa-f]+", text).group(0))
    try:
        return f"0x{int(text):02X}"
    except Exception:
        return text


def _extract_state_raw_value(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    match = re.match(r"\s*([^=:=\s]+)\s*[:=]", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


def _extract_numeric_value(text: str) -> Optional[int]:
    cleaned = _clean_text(text)
    if not cleaned:
        return None
    hex_match = re.search(r"0x([0-9A-Fa-f]+)", cleaned)
    if hex_match:
        try:
            return int(hex_match.group(1), 16)
        except Exception:
            return None
    prefix_match = re.match(r"\s*(-?\d+)\s*[:=]", cleaned)
    if prefix_match:
        try:
            return int(prefix_match.group(1))
        except Exception:
            return None
    if re.fullmatch(r"-?\d+", cleaned):
        try:
            return int(cleaned)
        except Exception:
            return None
    return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _is_empty_row(row: Tuple[Any, ...]) -> bool:
    return not any(_clean_text(cell) for cell in row)

