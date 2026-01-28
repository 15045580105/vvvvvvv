from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Callable

@dataclass
class DPTItem:
    byte: str
    bit: str
    sub_data_name_e: str
    sub_data_name_c: str
    conversion_e: str
    conversion_c: str
    encoding: str

    def get_parsed_conversions(self) -> Dict[str, str]:
        """
        Parses the conversion_c string into a dictionary.
        Example: "0=禁止\n1=使能" -> {"0": "禁止", "1": "使能"}
        Or "0x01=Enable" etc.
        """
        conversions = {}
        if not self.conversion_c or self.conversion_c == "-":
            return conversions

        # Handle different delimiters like "\n" or ";"
        # Based on dpt format: "0x00= 屏蔽\n0x01= 使能", "0=禁止\n1=使能"
        parts = self.conversion_c.split('\n')
        for part in parts:
            if '=' in part:
                 key, val = part.split('=', 1)
                 # Clean up keys like '0x01 ' or '0 '
                 key = key.strip()
                 # Handle hex keys
                 if key.startswith('0x'):
                     try:
                         # Normalize to int str? or keep as is?
                         # Request says: "0" in "0=禁止"
                         # Let's simple strip and use as string, but maybe caller needs int logic
                         pass
                     except:
                         pass
                 conversions[key] = val.strip()
        return conversions

@dataclass
class DPTDID:
    did_number: str
    description_e: str
    description_c: str
    items: List[DPTItem]
    raw_data: Dict[str, Any] = None  # Added to store raw JSON data

@dataclass
class DPTData:
    dids: Dict[str, DPTDID]

class DPTManager:
    """
    Manages loading and querying DPT configuration.
    """
    def __init__(self):
         self.dpt_data: Optional[DPTData] = None

    def load_dpt_from_file(self, file_path: str):
        import json
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Parse structure: root -> sheets -> "DID Table-$22&2E" -> dids
            # Note: The sheet name might vary, so we might need to iterate or check specific key.
            # Based on head output: "sheets": { "DID Table-$22&2E": { "dids": [ ...

            dids_map = {}

            sheets = data.get("sheets", {})
            for sheet_name, sheet_content in sheets.items():
                if "dids" in sheet_content:
                    dids_list = sheet_content["dids"]
                    for did_data in dids_list:
                        items_data = did_data.get("items", [])
                        dpt_items = []
                        for item in items_data:
                            dpt_item = DPTItem(
                                byte=str(item.get("byte", "")),
                                bit=str(item.get("bit", "")),
                                sub_data_name_e=item.get("sub_data_name_e", ""),
                                sub_data_name_c=item.get("sub_data_name_c", ""),
                                conversion_e=item.get("conversion_e", ""),
                                conversion_c=item.get("conversion_c", ""),
                                encoding=item.get("encoding", "")
                            )
                            dpt_items.append(dpt_item)

                        did_obj = DPTDID(
                            did_number=did_data.get("did_number", ""),
                            description_e=did_data.get("description_e", ""),
                            description_c=did_data.get("description_c", ""),
                            items=dpt_items,
                            raw_data=did_data  # Store raw data
                        )
                        dids_map[did_obj.did_number] = did_obj

            self.dpt_data = DPTData(dids=dids_map)

        except Exception as e:
            print(f"Error loading DPT file: {e}")
            self.dpt_data = None

    def calculate_byte_val(self, did_key: str, param_obj: str, param_state: str, log_callback: Optional[Callable[[str], None]] = None) -> Optional[bytes]:
        """
        Calculates byte value based on DID, Parameter Object Name(s), and Parameter State.
        """
        def _log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        if not self.dpt_data:
            return None

        # Normalize did_key
        search_key = did_key
        if not search_key.startswith("0x"):
             if any(k.endswith(search_key) for k in self.dpt_data.dids.keys()):
                 search_key = "0x" + did_key

        # Find DID Object
        did_obj = self.dpt_data.dids.get(search_key)
        if not did_obj:
            # Case insensitive search
            for k, v in self.dpt_data.dids.items():
                if k.lower() == search_key.lower():
                     did_obj = v
                     break

        if not did_obj:
            _log(f"DID {did_key} not found in DPT")
            return None

        # --- 新增逻辑：处理 ASCII 输入 ---
        # 检查是否为 ASCII 类型输入 (通常 param_obj 和 param_state 都是输入值)
        # 例如: byte="0~15", conversion="-", encoding="ASCII"
        is_ascii_input = False
        target_ascii_items = []

        # 简单 heuristic: 检查是否有 encoding="ASCII" 的 item 且 param_obj 匹配 sub_data_name
        # 或者 param_obj 本身就是输入值而不是选项名

        # 如果 param_obj 不是 "全选" 且找不到明确匹配的 Enum Item,
        # 但 DID 中存在 ASCII/Unsigned 且无 conversion 的 item, 则可能是直接赋值输入

        # 先尝试按名称匹配 (现有逻辑)
        target_items = []

        # Check for "All" / "已全选"
        if param_obj == "已全选" or param_obj.lower() == "all":
            # Filter out "Reserved" items if All is selected
            target_items = [
                item for item in did_obj.items
                if "reserved" not in item.sub_data_name_c.lower() and "reserved" not in item.sub_data_name_e.lower()
            ]
        else:
            # Split param_obj by comma (handle multi-select)
            obj_names = [n.strip() for n in param_obj.split(',')]

            for name in obj_names:
                found_item = None
                for item in did_obj.items:
                    # Check Chinese Name
                    if name == item.sub_data_name_c or name in item.sub_data_name_c:
                        found_item = item
                        break
                    # Fallback english
                    if name == item.sub_data_name_e or name in item.sub_data_name_e:
                        found_item = item
                        break

                if found_item:
                    target_items.append(found_item)
                else:
                    _log(f"Param Object '{name}' not found in DID {did_key}")

        if not target_items:
            _log(f"No matching items found for {param_obj}")
            return None

        # Find max byte to determine size upfront (needed for log and return)
        max_byte = 0
        if did_obj.items:
             for item in did_obj.items:
                 try:
                     b = int(item.byte)
                     if b > max_byte: max_byte = b
                 except: pass

        total_len = max_byte + 1

        # Calculate final combined value
        byte_values = {} # index -> val

        for item in target_items:
             # Resolve State Value for this item
             conversions = item.get_parsed_conversions()
             target_val = -1

             if target_val == -1:
                 # Default logic
                 # Check against parsed conversions
                 # param_state e.g. "使能", "禁止" etc.
                 # conversion e.g. {"0": "禁止", "1": "使能"}

                 found_in_conversion = False

                 # 1. 优先尝试严格完全匹配
                 for val_str, desc in conversions.items():
                     if param_state.strip() == desc.strip():
                           try:
                               if val_str.startswith("0x"):
                                   target_val = int(val_str, 16)
                               else:
                                   target_val = int(val_str)
                               found_in_conversion = True
                               break
                           except:
                               pass

                 # 2. 如果没有严格匹配，尝试反向包含 (Config desc IN user input)
                 # 例如: desc="带 TLS", input="带 TLS工作模式(推荐)" -> 若 "带 TLS" in input
                 # 注意：要避免短词误判，这步需谨慎。但在 "不带 TLS" vs "带 TLS" 场景中，如果不带 TLS 先被匹配了就可以
                 if not found_in_conversion:
                     # 对 conversions 按描述长度降序排序，优先匹配更长的描述，避免 "带 TLS" 误配 "不带 TLS" (如果 "不带" 没有先被匹配)
                     # 但由于 param_state 只有一份，我们是检查 desc 是否在 param_state 中
                     sorted_items = sorted(conversions.items(), key=lambda x: len(x[1]), reverse=True)
                     for val_str, desc in sorted_items:
                         if desc and desc.strip() and desc.strip() in param_state:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 # 3. 最后尝试正向包含 (User input IN config desc)
                 if not found_in_conversion:
                     for val_str, desc in conversions.items():
                          if param_state and param_state.strip() and param_state.strip() in desc:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 if not found_in_conversion:
                     # 优化逻辑：优先从字符串中提取数值 (Hex/Int)，处理如 "TLS模式(0x01)" 或 "Mode 2" 等动态格式
                     import re

                     # 1. 尝试提取 Hex (0x...)
                     hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state)
                     if hex_match:
                         try:
                             target_val = int(hex_match.group(1), 16)
                         except: pass

                     if target_val == -1:
                         # 2. 尝试提取纯数字
                         # 简单策略：提取所有数字序列，使用最后一个 (通常是想要的值，如 "Mode 1" -> 1)
                         nums = re.findall(r"\d+", param_state)
                         if nums:
                             try:
                                 # 避免提取到像 DID 这样的大数字 (如果需要的话可以限制长度，但这里暂不限制)
                                 target_val = int(nums[-1])
                             except: pass

                     # 3. 如果仍未解析出数值，回退到关键词匹配
                     if target_val == -1:
                         # 默认的基础关键词
                         neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "不使能"]
                         pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON"]

                         # 动态从当前 item 的 conversions 中获取 0 和 1 的描述
                         # 这样可以支持 "Deactivated", "Inactive" 等自定义描述
                         for c_key, c_desc in conversions.items():
                             try:
                                 # 解析 key (支持 0, 0x00, 1, 0x01 等格式)
                                 val_i = int(c_key, 16) if c_key.startswith("0x") else int(c_key)

                                 # 清理描述文本
                                 desc_clean = c_desc.strip()
                                 if not desc_clean: continue

                                 if val_i == 0:
                                     if desc_clean not in neg_keys:
                                         neg_keys.append(desc_clean)
                                 elif val_i == 1:
                                     if desc_clean not in pos_keys:
                                         pos_keys.append(desc_clean)
                             except:
                                 pass

                         # 进行关键词匹配
                         if any(k in param_state for k in neg_keys):
                             target_val = 0
                         elif any(k in param_state for k in pos_keys):
                             target_val = 1

             if target_val != -1:
                try:
                    if item.bit.lower() == "all":
                        byte_curr = int(item.byte)
                    else:
                        byte_curr = int(item.byte)
                except:
                    byte_curr = 0

                bit_str = item.bit.lower()
                start_bit = 0
                if bit_str == "all":
                    start_bit = 0
                elif "~" in bit_str:
                     parts = bit_str.split("~")
                     try:
                         p1 = int(parts[0])
                         p2 = int(parts[1])
                         start_bit = min(p1, p2)
                     except:
                         start_bit = 0
                else:
                     try:
                        start_bit = int(bit_str)
                     except:
                        start_bit = 0

                current_byte_val = byte_values.get(byte_curr, 0)
                current_byte_val |= (target_val << start_bit)
                byte_values[byte_curr] = current_byte_val

        # Assemble final_bytes
        final_val_int = 0
        for b_idx in range(total_len):
            val = byte_values.get(b_idx, 0)
            shift = (total_len - 1 - b_idx) * 8
            final_val_int |= (val << shift)

        _log(f"[{did_key}] 参数对象:{param_obj},参数状态:{param_state}, DPT计算结果（hex）: {final_val_int:0{total_len*2}X} (Bin: {final_val_int:0{total_len*8}b})")

        # --- 新逻辑：处理 ASCII 输入 ---
        # 检查是否为 ASCII 类型输入 (通常 param_obj 和 param_state 都是输入值)
        # 例如: byte="0~15", conversion="-", encoding="ASCII"
        is_ascii_input = False
        target_ascii_items = []

        # 简单 heuristic: 检查是否有 encoding="ASCII" 的 item 且 param_obj 匹配 sub_data_name
        # 或者 param_obj 本身就是输入值而不是选项名

        # 如果 param_obj 不是 "全选" 且找不到明确匹配的 Enum Item,
        # 但 DID 中存在 ASCII/Unsigned 且无 conversion 的 item, 则可能是直接赋值输入

        # 先尝试按名称匹配 (现有逻辑)
        target_items = []

        # Check for "All" / "已全选"
        if param_obj == "已全选" or param_obj.lower() == "all":
            # Filter out "Reserved" items if All is selected
            target_items = [
                item for item in did_obj.items
                if "reserved" not in item.sub_data_name_c.lower() and "reserved" not in item.sub_data_name_e.lower()
            ]
        else:
            # Split param_obj by comma (handle multi-select)
            obj_names = [n.strip() for n in param_obj.split(',')]

            for name in obj_names:
                found_item = None
                for item in did_obj.items:
                    # Check Chinese Name
                    if name == item.sub_data_name_c or name in item.sub_data_name_c:
                        found_item = item
                        break
                    # Fallback english
                    if name == item.sub_data_name_e or name in item.sub_data_name_e:
                        found_item = item
                        break

                if found_item:
                    target_items.append(found_item)
                else:
                    _log(f"Param Object '{name}' not found in DID {did_key}")

        if not target_items:
            _log(f"No matching items found for {param_obj}")
            return None

        # Find max byte to determine size upfront (needed for log and return)
        max_byte = 0
        if did_obj.items:
             for item in did_obj.items:
                 try:
                     b = int(item.byte)
                     if b > max_byte: max_byte = b
                 except: pass

        total_len = max_byte + 1

        # Calculate final combined value
        byte_values = {} # index -> val

        for item in target_items:
             # Resolve State Value for this item
             conversions = item.get_parsed_conversions()
             target_val = -1

             if target_val == -1:
                 # Default logic
                 # Check against parsed conversions
                 # param_state e.g. "使能", "禁止" etc.
                 # conversion e.g. {"0": "禁止", "1": "使能"}

                 found_in_conversion = False

                 # 1. 优先尝试严格完全匹配
                 for val_str, desc in conversions.items():
                     if param_state.strip() == desc.strip():
                           try:
                               if val_str.startswith("0x"):
                                   target_val = int(val_str, 16)
                               else:
                                   target_val = int(val_str)
                               found_in_conversion = True
                               break
                           except:
                               pass

                 # 2. 如果没有严格匹配，尝试反向包含 (Config desc IN user input)
                 # 例如: desc="带 TLS", input="带 TLS工作模式(推荐)" -> 若 "带 TLS" in input
                 # 注意：要避免短词误判，这步需谨慎。但在 "不带 TLS" vs "带 TLS" 场景中，如果不带 TLS 先被匹配了就可以
                 if not found_in_conversion:
                     # 对 conversions 按描述长度降序排序，优先匹配更长的描述，避免 "带 TLS" 误配 "不带 TLS" (如果 "不带" 没有先被匹配)
                     # 但由于 param_state 只有一份，我们是检查 desc 是否在 param_state 中
                     sorted_items = sorted(conversions.items(), key=lambda x: len(x[1]), reverse=True)
                     for val_str, desc in sorted_items:
                         if desc and desc.strip() and desc.strip() in param_state:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 # 3. 最后尝试正向包含 (User input IN config desc)
                 if not found_in_conversion:
                     for val_str, desc in conversions.items():
                          if param_state and param_state.strip() and param_state.strip() in desc:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 if not found_in_conversion:
                     # 优化逻辑：优先从字符串中提取数值 (Hex/Int)，处理如 "TLS模式(0x01)" 或 "Mode 2" 等动态格式
                     import re

                     # 1. 尝试提取 Hex (0x...)
                     hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state)
                     if hex_match:
                         try:
                             target_val = int(hex_match.group(1), 16)
                         except: pass

                     if target_val == -1:
                         # 2. 尝试提取纯数字
                         # 简单策略：提取所有数字序列，使用最后一个 (通常是想要的值，如 "Mode 1" -> 1)
                         nums = re.findall(r"\d+", param_state)
                         if nums:
                             try:
                                 # 避免提取到像 DID 这样的大数字 (如果需要的话可以限制长度，但这里暂不限制)
                                 target_val = int(nums[-1])
                             except: pass

                     # 3. 如果仍未解析出数值，回退到关键词匹配
                     if target_val == -1:
                         # 默认的基础关键词
                         neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "不使能"]
                         pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON"]

                         # 动态从当前 item 的 conversions 中获取 0 和 1 的描述
                         # 这样可以支持 "Deactivated", "Inactive" 等自定义描述
                         for c_key, c_desc in conversions.items():
                             try:
                                 # 解析 key (支持 0, 0x00, 1, 0x01 等格式)
                                 val_i = int(c_key, 16) if c_key.startswith("0x") else int(c_key)

                                 # 清理描述文本
                                 desc_clean = c_desc.strip()
                                 if not desc_clean: continue

                                 if val_i == 0:
                                     if desc_clean not in neg_keys:
                                         neg_keys.append(desc_clean)
                                 elif val_i == 1:
                                     if desc_clean not in pos_keys:
                                         pos_keys.append(desc_clean)
                             except:
                                 pass

                         # 进行关键词匹配
                         if any(k in param_state for k in neg_keys):
                             target_val = 0
                         elif any(k in param_state for k in pos_keys):
                             target_val = 1

             if target_val != -1:
                try:
                    if item.bit.lower() == "all":
                        byte_curr = int(item.byte)
                    else:
                        byte_curr = int(item.byte)
                except:
                    byte_curr = 0

                bit_str = item.bit.lower()
                start_bit = 0
                if bit_str == "all":
                    start_bit = 0
                elif "~" in bit_str:
                     parts = bit_str.split("~")
                     try:
                         p1 = int(parts[0])
                         p2 = int(parts[1])
                         start_bit = min(p1, p2)
                     except:
                         start_bit = 0
                else:
                     try:
                        start_bit = int(bit_str)
                     except:
                        start_bit = 0

                current_byte_val = byte_values.get(byte_curr, 0)
                current_byte_val |= (target_val << start_bit)
                byte_values[byte_curr] = current_byte_val

        # --- 新逻辑：处理 ASCII 输入 ---
        # 检查是否为 ASCII 类型输入 (通常 param_obj 和 param_state 都是输入值)
        # 例如: byte="0~15", conversion="-", encoding="ASCII"
        is_ascii_input = False
        target_ascii_items = []

        # 简单 heuristic: 检查是否有 encoding="ASCII" 的 item 且 param_obj 匹配 sub_data_name
        # 或者 param_obj 本身就是输入值而不是选项名

        # 如果 param_obj 不是 "全选" 且找不到明确匹配的 Enum Item,
        # 但 DID 中存在 ASCII/Unsigned 且无 conversion 的 item, 则可能是直接赋值输入

        # 先尝试按名称匹配 (现有逻辑)
        target_items = []

        # Check for "All" / "已全选"
        if param_obj == "已全选" or param_obj.lower() == "all":
            # Filter out "Reserved" items if All is selected
            target_items = [
                item for item in did_obj.items
                if "reserved" not in item.sub_data_name_c.lower() and "reserved" not in item.sub_data_name_e.lower()
            ]
        else:
            # Split param_obj by comma (handle multi-select)
            obj_names = [n.strip() for n in param_obj.split(',')]

            for name in obj_names:
                found_item = None
                for item in did_obj.items:
                    # Check Chinese Name
                    if name == item.sub_data_name_c or name in item.sub_data_name_c:
                        found_item = item
                        break
                    # Fallback english
                    if name == item.sub_data_name_e or name in item.sub_data_name_e:
                        found_item = item
                        break

                if found_item:
                    target_items.append(found_item)
                else:
                    _log(f"Param Object '{name}' not found in DID {did_key}")

        if not target_items:
            _log(f"No matching items found for {param_obj}")
            return None

        # Find max byte to determine size upfront (needed for log and return)
        max_byte = 0
        if did_obj.items:
             for item in did_obj.items:
                 try:
                     b = int(item.byte)
                     if b > max_byte: max_byte = b
                 except: pass

        total_len = max_byte + 1

        # Calculate final combined value
        byte_values = {} # index -> val

        for item in target_items:
             # Resolve State Value for this item
             conversions = item.get_parsed_conversions()
             target_val = -1

             if target_val == -1:
                 # Default logic
                 # Check against parsed conversions
                 # param_state e.g. "使能", "禁止" etc.
                 # conversion e.g. {"0": "禁止", "1": "使能"}

                 found_in_conversion = False

                 # 1. 优先尝试严格完全匹配
                 for val_str, desc in conversions.items():
                     if param_state.strip() == desc.strip():
                           try:
                               if val_str.startswith("0x"):
                                   target_val = int(val_str, 16)
                               else:
                                   target_val = int(val_str)
                               found_in_conversion = True
                               break
                           except:
                               pass

                 # 2. 如果没有严格匹配，尝试反向包含 (Config desc IN user input)
                 # 例如: desc="带 TLS", input="带 TLS工作模式(推荐)" -> 若 "带 TLS" in input
                 # 注意：要避免短词误判，这步需谨慎。但在 "不带 TLS" vs "带 TLS" 场景中，如果不带 TLS 先被匹配了就可以
                 if not found_in_conversion:
                     # 对 conversions 按描述长度降序排序，优先匹配更长的描述，避免 "带 TLS" 误配 "不带 TLS" (如果 "不带" 没有先被匹配)
                     # 但由于 param_state 只有一份，我们是检查 desc 是否在 param_state 中
                     sorted_items = sorted(conversions.items(), key=lambda x: len(x[1]), reverse=True)
                     for val_str, desc in sorted_items:
                         if desc and desc.strip() and desc.strip() in param_state:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 # 3. 最后尝试正向包含 (User input IN config desc)
                 if not found_in_conversion:
                     for val_str, desc in conversions.items():
                          if param_state and param_state.strip() and param_state.strip() in desc:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 if not found_in_conversion:
                     # 优化逻辑：优先从字符串中提取数值 (Hex/Int)，处理如 "TLS模式(0x01)" 或 "Mode 2" 等动态格式
                     import re

                     # 1. 尝试提取 Hex (0x...)
                     hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state)
                     if hex_match:
                         try:
                             target_val = int(hex_match.group(1), 16)
                         except: pass

                     if target_val == -1:
                         # 2. 尝试提取纯数字
                         # 简单策略：提取所有数字序列，使用最后一个 (通常是想要的值，如 "Mode 1" -> 1)
                         nums = re.findall(r"\d+", param_state)
                         if nums:
                             try:
                                 # 避免提取到像 DID 这样的大数字 (如果需要的话可以限制长度，但这里暂不限制)
                                 target_val = int(nums[-1])
                             except: pass

                     # 3. 如果仍未解析出数值，回退到关键词匹配
                     if target_val == -1:
                         # 默认的基础关键词
                         neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "不使能"]
                         pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON"]

                         # 动态从当前 item 的 conversions 中获取 0 和 1 的描述
                         # 这样可以支持 "Deactivated", "Inactive" 等自定义描述
                         for c_key, c_desc in conversions.items():
                             try:
                                 # 解析 key (支持 0, 0x00, 1, 0x01 等格式)
                                 val_i = int(c_key, 16) if c_key.startswith("0x") else int(c_key)

                                 # 清理描述文本
                                 desc_clean = c_desc.strip()
                                 if not desc_clean: continue

                                 if val_i == 0:
                                     if desc_clean not in neg_keys:
                                         neg_keys.append(desc_clean)
                                 elif val_i == 1:
                                     if desc_clean not in pos_keys:
                                         pos_keys.append(desc_clean)
                             except:
                                 pass

                         # 进行关键词匹配
                         if any(k in param_state for k in neg_keys):
                             target_val = 0
                         elif any(k in param_state for k in pos_keys):
                             target_val = 1

             if target_val != -1:
                try:
                    if item.bit.lower() == "all":
                        byte_curr = int(item.byte)
                    else:
                        byte_curr = int(item.byte)
                except:
                    byte_curr = 0

                bit_str = item.bit.lower()
                start_bit = 0
                if bit_str == "all":
                    start_bit = 0
                elif "~" in bit_str:
                     parts = bit_str.split("~")
                     try:
                         p1 = int(parts[0])
                         p2 = int(parts[1])
                         start_bit = min(p1, p2)
                     except:
                         start_bit = 0
                else:
                     try:
                        start_bit = int(bit_str)
                     except:
                        start_bit = 0

                current_byte_val = byte_values.get(byte_curr, 0)
                current_byte_val |= (target_val << start_bit)
                byte_values[byte_curr] = current_byte_val

        # --- 新逻辑：处理 ASCII 输入 ---
        # 检查是否为 ASCII 类型输入 (通常 param_obj 和 param_state 都是输入值)
        # 例如: byte="0~15", conversion="-", encoding="ASCII"
        is_ascii_input = False
        target_ascii_items = []

        # 简单 heuristic: 检查是否有 encoding="ASCII" 的 item 且 param_obj 匹配 sub_data_name
        # 或者 param_obj 本身就是输入值而不是选项名

        # 如果 param_obj 不是 "全选" 且找不到明确匹配的 Enum Item,
        # 但 DID 中存在 ASCII/Unsigned 且无 conversion 的 item, 则可能是直接赋值输入

        # 先尝试按名称匹配 (现有逻辑)
        target_items = []

        # Check for "All" / "已全选"
        if param_obj == "已全选" or param_obj.lower() == "all":
            # Filter out "Reserved" items if All is selected
            target_items = [
                item for item in did_obj.items
                if "reserved" not in item.sub_data_name_c.lower() and "reserved" not in item.sub_data_name_e.lower()
            ]
        else:
            # Split param_obj by comma (handle multi-select)
            obj_names = [n.strip() for n in param_obj.split(',')]

            for name in obj_names:
                found_item = None
                for item in did_obj.items:
                    # Check Chinese Name
                    if name == item.sub_data_name_c or name in item.sub_data_name_c:
                        found_item = item
                        break
                    # Fallback english
                    if name == item.sub_data_name_e or name in item.sub_data_name_e:
                        found_item = item
                        break

                if found_item:
                    target_items.append(found_item)
                else:
                    _log(f"Param Object '{name}' not found in DID {did_key}")

        if not target_items:
            _log(f"No matching items found for {param_obj}")
            return None

        # Find max byte to determine size upfront (needed for log and return)
        max_byte = 0
        if did_obj.items:
             for item in did_obj.items:
                 try:
                     b = int(item.byte)
                     if b > max_byte: max_byte = b
                 except: pass

        total_len = max_byte + 1

        # Calculate final combined value
        byte_values = {} # index -> val

        for item in target_items:
             # Resolve State Value for this item
             conversions = item.get_parsed_conversions()
             target_val = -1

             if target_val == -1:
                 # Default logic
                 # Check against parsed conversions
                 # param_state e.g. "使能", "禁止" etc.
                 # conversion e.g. {"0": "禁止", "1": "使能"}

                 found_in_conversion = False

                 # 1. 优先尝试严格完全匹配
                 for val_str, desc in conversions.items():
                     if param_state.strip() == desc.strip():
                           try:
                               if val_str.startswith("0x"):
                                   target_val = int(val_str, 16)
                               else:
                                   target_val = int(val_str)
                               found_in_conversion = True
                               break
                           except:
                               pass

                 # 2. 如果没有严格匹配，尝试反向包含 (Config desc IN user input)
                 # 例如: desc="带 TLS", input="带 TLS工作模式(推荐)" -> 若 "带 TLS" in input
                 # 注意：要避免短词误判，这步需谨慎。但在 "不带 TLS" vs "带 TLS" 场景中，如果不带 TLS 先被匹配了就可以
                 if not found_in_conversion:
                     # 对 conversions 按描述长度降序排序，优先匹配更长的描述，避免 "带 TLS" 误配 "不带 TLS" (如果 "不带" 没有先被匹配)
                     # 但由于 param_state 只有一份，我们是检查 desc 是否在 param_state 中
                     sorted_items = sorted(conversions.items(), key=lambda x: len(x[1]), reverse=True)
                     for val_str, desc in sorted_items:
                         if desc and desc.strip() and desc.strip() in param_state:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 # 3. 最后尝试正向包含 (User input IN config desc)
                 if not found_in_conversion:
                     for val_str, desc in conversions.items():
                          if param_state and param_state.strip() and param_state.strip() in desc:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 if not found_in_conversion:
                     # 优化逻辑：优先从字符串中提取数值 (Hex/Int)，处理如 "TLS模式(0x01)" 或 "Mode 2" 等动态格式
                     import re

                     # 1. 尝试提取 Hex (0x...)
                     hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state)
                     if hex_match:
                         try:
                             target_val = int(hex_match.group(1), 16)
                         except: pass

                     if target_val == -1:
                         # 2. 尝试提取纯数字
                         # 简单策略：提取所有数字序列，使用最后一个 (通常是想要的值，如 "Mode 1" -> 1)
                         nums = re.findall(r"\d+", param_state)
                         if nums:
                             try:
                                 # 避免提取到像 DID 这样的大数字 (如果需要的话可以限制长度，但这里暂不限制)
                                 target_val = int(nums[-1])
                             except: pass

                     # 3. 如果仍未解析出数值，回退到关键词匹配
                     if target_val == -1:
                         # 默认的基础关键词
                         neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "不使能"]
                         pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON"]

                         # 动态从当前 item 的 conversions 中获取 0 和 1 的描述
                         # 这样可以支持 "Deactivated", "Inactive" 等自定义描述
                         for c_key, c_desc in conversions.items():
                             try:
                                 # 解析 key (支持 0, 0x00, 1, 0x01 等格式)
                                 val_i = int(c_key, 16) if c_key.startswith("0x") else int(c_key)

                                 # 清理描述文本
                                 desc_clean = c_desc.strip()
                                 if not desc_clean: continue

                                 if val_i == 0:
                                     if desc_clean not in neg_keys:
                                         neg_keys.append(desc_clean)
                                 elif val_i == 1:
                                     if desc_clean not in pos_keys:
                                         pos_keys.append(desc_clean)
                             except:
                                 pass

                         # 进行关键词匹配
                         if any(k in param_state for k in neg_keys):
                             target_val = 0
                         elif any(k in param_state for k in pos_keys):
                             target_val = 1

             if target_val != -1:
                try:
                    if item.bit.lower() == "all":
                        byte_curr = int(item.byte)
                    else:
                        byte_curr = int(item.byte)
                except:
                    byte_curr = 0

                bit_str = item.bit.lower()
                start_bit = 0
                if bit_str == "all":
                    start_bit = 0
                elif "~" in bit_str:
                     parts = bit_str.split("~")
                     try:
                         p1 = int(parts[0])
                         p2 = int(parts[1])
                         start_bit = min(p1, p2)
                     except:
                         start_bit = 0
                else:
                     try:
                        start_bit = int(bit_str)
                     except:
                        start_bit = 0

                current_byte_val = byte_values.get(byte_curr, 0)
                current_byte_val |= (target_val << start_bit)
                byte_values[byte_curr] = current_byte_val

        # --- 新逻辑：处理 ASCII 输入 ---
        # 检查是否为 ASCII 类型输入 (通常 param_obj 和 param_state 都是输入值)
        # 例如: byte="0~15", conversion="-", encoding="ASCII"
        is_ascii_input = False
        target_ascii_items = []

        # 简单 heuristic: 检查是否有 encoding="ASCII" 的 item 且 param_obj 匹配 sub_data_name
        # 或者 param_obj 本身就是输入值而不是选项名

        # 如果 param_obj 不是 "全选" 且找不到明确匹配的 Enum Item,
        # 但 DID 中存在 ASCII/Unsigned 且无 conversion 的 item, 则可能是直接赋值输入

        # 先尝试按名称匹配 (现有逻辑)
        target_items = []

        # Check for "All" / "已全选"
        if param_obj == "已全选" or param_obj.lower() == "all":
            # Filter out "Reserved" items if All is selected
            target_items = [
                item for item in did_obj.items
                if "reserved" not in item.sub_data_name_c.lower() and "reserved" not in item.sub_data_name_e.lower()
            ]
        else:
            # Split param_obj by comma (handle multi-select)
            obj_names = [n.strip() for n in param_obj.split(',')]

            for name in obj_names:
                found_item = None
                for item in did_obj.items:
                    # Check Chinese Name
                    if name == item.sub_data_name_c or name in item.sub_data_name_c:
                        found_item = item
                        break
                    # Fallback english
                    if name == item.sub_data_name_e or name in item.sub_data_name_e:
                        found_item = item
                        break

                if found_item:
                    target_items.append(found_item)
                else:
                    _log(f"Param Object '{name}' not found in DID {did_key}")

        if not target_items:
            _log(f"No matching items found for {param_obj}")
            return None

        # Find max byte to determine size upfront (needed for log and return)
        max_byte = 0
        if did_obj.items:
             for item in did_obj.items:
                 try:
                     b = int(item.byte)
                     if b > max_byte: max_byte = b
                 except: pass

        total_len = max_byte + 1

        # Calculate final combined value
        byte_values = {} # index -> val

        for item in target_items:
             # Resolve State Value for this item
             conversions = item.get_parsed_conversions()
             target_val = -1

             if target_val == -1:
                 # Default logic
                 # Check against parsed conversions
                 # param_state e.g. "使能", "禁止" etc.
                 # conversion e.g. {"0": "禁止", "1": "使能"}

                 found_in_conversion = False

                 # 1. 优先尝试严格完全匹配
                 for val_str, desc in conversions.items():
                     if param_state.strip() == desc.strip():
                           try:
                               if val_str.startswith("0x"):
                                   target_val = int(val_str, 16)
                               else:
                                   target_val = int(val_str)
                               found_in_conversion = True
                               break
                           except:
                               pass

                 # 2. 如果没有严格匹配，尝试反向包含 (Config desc IN user input)
                 # 例如: desc="带 TLS", input="带 TLS工作模式(推荐)" -> 若 "带 TLS" in input
                 # 注意：要避免短词误判，这步需谨慎。但在 "不带 TLS" vs "带 TLS" 场景中，如果不带 TLS 先被匹配了就可以
                 if not found_in_conversion:
                     # 对 conversions 按描述长度降序排序，优先匹配更长的描述，避免 "带 TLS" 误配 "不带 TLS" (如果 "不带" 没有先被匹配)
                     # 但由于 param_state 只有一份，我们是检查 desc 是否在 param_state 中
                     sorted_items = sorted(conversions.items(), key=lambda x: len(x[1]), reverse=True)
                     for val_str, desc in sorted_items:
                         if desc and desc.strip() and desc.strip() in param_state:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 # 3. 最后尝试正向包含 (User input IN config desc)
                 if not found_in_conversion:
                     for val_str, desc in conversions.items():
                          if param_state and param_state.strip() and param_state.strip() in desc:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 if not found_in_conversion:
                     # 优化逻辑：优先从字符串中提取数值 (Hex/Int)，处理如 "TLS模式(0x01)" 或 "Mode 2" 等动态格式
                     import re

                     # 1. 尝试提取 Hex (0x...)
                     hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state)
                     if hex_match:
                         try:
                             target_val = int(hex_match.group(1), 16)
                         except: pass

                     if target_val == -1:
                         # 2. 尝试提取纯数字
                         # 简单策略：提取所有数字序列，使用最后一个 (通常是想要的值，如 "Mode 1" -> 1)
                         nums = re.findall(r"\d+", param_state)
                         if nums:
                             try:
                                 # 避免提取到像 DID 这样的大数字 (如果需要的话可以限制长度，但这里暂不限制)
                                 target_val = int(nums[-1])
                             except: pass

                     # 3. 如果仍未解析出数值，回退到关键词匹配
                     if target_val == -1:
                         # 默认的基础关键词
                         neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "不使能"]
                         pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON"]

                         # 动态从当前 item 的 conversions 中获取 0 和 1 的描述
                         # 这样可以支持 "Deactivated", "Inactive" 等自定义描述
                         for c_key, c_desc in conversions.items():
                             try:
                                 # 解析 key (支持 0, 0x00, 1, 0x01 等格式)
                                 val_i = int(c_key, 16) if c_key.startswith("0x") else int(c_key)

                                 # 清理描述文本
                                 desc_clean = c_desc.strip()
                                 if not desc_clean: continue

                                 if val_i == 0:
                                     if desc_clean not in neg_keys:
                                         neg_keys.append(desc_clean)
                                 elif val_i == 1:
                                     if desc_clean not in pos_keys:
                                         pos_keys.append(desc_clean)
                             except:
                                 pass

                         # 进行关键词匹配
                         if any(k in param_state for k in neg_keys):
                             target_val = 0
                         elif any(k in param_state for k in pos_keys):
                             target_val = 1

             if target_val != -1:
                try:
                    if item.bit.lower() == "all":
                        byte_curr = int(item.byte)
                    else:
                        byte_curr = int(item.byte)
                except:
                    byte_curr = 0

                bit_str = item.bit.lower()
                start_bit = 0
                if bit_str == "all":
                    start_bit = 0
                elif "~" in bit_str:
                     parts = bit_str.split("~")
                     try:
                         p1 = int(parts[0])
                         p2 = int(parts[1])
                         start_bit = min(p1, p2)
                     except:
                         start_bit = 0
                else:
                     try:
                        start_bit = int(bit_str)
                     except:
                        start_bit = 0

                current_byte_val = byte_values.get(byte_curr, 0)
                current_byte_val |= (target_val << start_bit)
                byte_values[byte_curr] = current_byte_val

        # Check if we should handle as ASCII/Direct Value
        # If item encoding is ASCII and conversion is "-"

        # We need a buffer to hold all bytes
        # First calculate total size
        max_byte_idx = 0
        for item in did_obj.items: # Look at all items to size reference
             # Parse byte range "0~15"
             if "~" in item.byte:
                 try:
                    end_b = int(item.byte.split("~")[1])
                    max_byte_idx = max(max_byte_idx, end_b)
                 except: pass
             else:
                 try:
                    max_byte_idx = max(max_byte_idx, int(item.byte))
                 except: pass

        total_len = max_byte_idx + 1
        final_bytes = bytearray(total_len)

        # Track which bytes are set to avoid overwriting (or minimal conflict)
        bytes_set = [False] * total_len

        for item in target_items:
             # Calculate offset and length for this item
             start_byte = 0
             end_byte = 0
             length = 1

             if "~" in item.byte:
                 try:
                     parts = item.byte.split("~")
                     start_byte = int(parts[0])
                     end_byte = int(parts[1])
                     length = end_byte - start_byte + 1
                 except:
                     start_byte = int(item.byte) if item.byte.isdigit() else 0
                     end_byte = start_byte
             else:
                 start_byte = int(item.byte) if item.byte.isdigit() else 0
                 end_byte = start_byte

             # Logic for ASCII / Raw String
             if item.encoding == "ASCII" or (item.conversion_c == "-" and item.conversion_e == "-"):
                 # Handle param_state as the value string
                 val_str = str(param_state)

                 # Encode
                 encoded_val = val_str.encode('ascii', errors='ignore') # Or 'replace'?

                 # Truncate or Pad
                 if len(encoded_val) > length:
                     encoded_val = encoded_val[:length]
                 elif len(encoded_val) < length:
                     # Pad with 0x00? or Space 0x20? Usually 0x00 for C-string style or fixed
                     encoded_val = encoded_val + b'\x00' * (length - len(encoded_val))

                 # Place into final_bytes
                 for i, b in enumerate(encoded_val):
                     if start_byte + i < total_len:
                         final_bytes[start_byte + i] = b
                         bytes_set[start_byte + i] = True

                 _log(f"Encoded '{val_str}' to ASCII bytes (len={length}): {encoded_val.hex().upper()}")
                 continue

             # Resolve State Value for this item (Standard Enum/Int Logic)
             conversions = item.get_parsed_conversions()
             target_val = -1

             if target_val == -1:
                 # Default logic
                 # Check against parsed conversions
                 # param_state e.g. "使能", "禁止" etc.
                 # conversion e.g. {"0": "禁止", "1": "使能"}

                 found_in_conversion = False

                 # 1. 优先尝试严格完全匹配
                 for val_str, desc in conversions.items():
                     if param_state.strip() == desc.strip():
                           try:
                               if val_str.startswith("0x"):
                                   target_val = int(val_str, 16)
                               else:
                                   target_val = int(val_str)
                               found_in_conversion = True
                               break
                           except:
                               pass

                 # 2. 如果没有严格匹配，尝试反向包含 (Config desc IN user input)
                 # 例如: desc="带 TLS", input="带 TLS工作模式(推荐)" -> 若 "带 TLS" in input
                 # 注意：要避免短词误判，这步需谨慎。但在 "不带 TLS" vs "带 TLS" 场景中，如果不带 TLS 先被匹配了就可以
                 if not found_in_conversion:
                     # 对 conversions 按描述长度降序排序，优先匹配更长的描述，避免 "带 TLS" 误配 "不带 TLS" (如果 "不带" 没有先被匹配)
                     # 但由于 param_state 只有一份，我们是检查 desc 是否在 param_state 中
                     sorted_items = sorted(conversions.items(), key=lambda x: len(x[1]), reverse=True)
                     for val_str, desc in sorted_items:
                         if desc and desc.strip() and desc.strip() in param_state:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 # 3. 最后尝试正向包含 (User input IN config desc)
                 if not found_in_conversion:
                     for val_str, desc in conversions.items():
                          if param_state and param_state.strip() and param_state.strip() in desc:
                               try:
                                   if val_str.startswith("0x"):
                                       target_val = int(val_str, 16)
                                   else:
                                       target_val = int(val_str)
                                   found_in_conversion = True
                                   break
                               except:
                                   pass

                 if not found_in_conversion:
                     # 优化逻辑：优先从字符串中提取数值 (Hex/Int)，处理如 "TLS模式(0x01)" 或 "Mode 2" 等动态格式
                     import re

                     # 1. 尝试提取 Hex (0x...)
                     hex_match = re.search(r"0x([0-9A-Fa-f]+)", param_state)
                     if hex_match:
                         try:
                             target_val = int(hex_match.group(1), 16)
                         except: pass

                     if target_val == -1:
                         # 2. 尝试提取纯数字
                         # 简单策略：提取所有数字序列，使用最后一个 (通常是想要的值，如 "Mode 1" -> 1)
                         nums = re.findall(r"\d+", param_state)
                         if nums:
                             try:
                                 # 避免提取到像 DID 这样的大数字 (如果需要的话可以限制长度，但这里暂不限制)
                                 target_val = int(nums[-1])
                             except: pass

                     # 3. 如果仍未解析出数值，回退到关键词匹配
                     if target_val == -1:
                         # 默认的基础关键词
                         neg_keys = ["禁止", "Disable", "关闭", "Close", "Off", "OFF", "不使能"]
                         pos_keys = ["使能", "Enable", "打开", "Open", "On", "ON"]

                         # 动态从当前 item 的 conversions 中获取 0 和 1 的描述
                         # 这样可以支持 "Deactivated", "Inactive" 等自定义描述
                         for c_key, c_desc in conversions.items():
                             try:
                                 # 解析 key (支持 0, 0x00, 1, 0x01 等格式)
                                 val_i = int(c_key, 16) if c_key.startswith("0x") else int(c_key)

                                 # 清理描述文本
                                 desc_clean = c_desc.strip()
                                 if not desc_clean: continue

                                 if val_i == 0:
                                     if desc_clean not in neg_keys:
                                         neg_keys.append(desc_clean)
                                 elif val_i == 1:
                                     if desc_clean not in pos_keys:
                                         pos_keys.append(desc_clean)
                             except:
                                 pass

                         # 进行关键词匹配
                         if any(k in param_state for k in neg_keys):
                             target_val = 0
                         elif any(k in param_state for k in pos_keys):
                             target_val = 1

             if target_val != -1:
                # Bit shifting logic for standard items
                # Need to map byte_curr (relative or absolute?)
                # Existing logic assumes single byte items or manual bit ops
                # If item spans multiple bytes with 'bit' definition, standard logic applies per byte?
                # Usually standard items are 1 byte or specific bits in 1 byte.

                try:
                    byte_curr = int(item.byte)
                    current_byte_val = final_bytes[byte_curr]
                    # ...existing bit shift logic...
                    # update final_bytes[byte_curr]

                    bit_str = item.bit.lower()
                    start_bit = 0
                    if bit_str == "all":
                        start_bit = 0
                    elif "~" in bit_str:
                         parts = bit_str.split("~")
                         try:
                             p1 = int(parts[0])
                             p2 = int(parts[1])
                             # DPT usually uses bit 0 as LSB? or MSB?
                             # Standard assumes bit 0 is LSB of the byte.
                             start_bit = min(p1, p2)
                         except:
                             start_bit = 0
                    else:
                         try:
                            start_bit = int(bit_str)
                         except:
                            start_bit = 0

                    current_byte_val |= (target_val << start_bit)
                    final_bytes[byte_curr] = current_byte_val
                    bytes_set[byte_curr] = True

                except:
                    pass

        # return final_val_int.to_bytes(...) -> return bytes(final_bytes)

        _log(f"[{did_key}] DPT Direct Result: {final_bytes.hex(' ').upper()}")
        return bytes(final_bytes)
