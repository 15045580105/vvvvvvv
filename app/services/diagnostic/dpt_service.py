from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ProcessPoolExecutor

from app.common.utils.DPTUtils import DPTParser, DPTParseResult
from app.core.dependency_injection import di_container
from app.services.configuration.config_service import AppConfigurationService

# --- Helper functions for subprocess parsing ---

def _parse_range(val: Any) -> tuple[int, int]:
    """Returns (start, length). If 'All' or invalid, returns (-1, -1)."""
    if val is None: return -1, -1
    s = str(val).strip().lower()
    if s == "all": return -1, -1

    separator = None
    if "~" in s: separator = "~"
    elif "-" in s: separator = "-"

    if separator:
        parts = s.split(separator)
        try:
            start = int(parts[0])
            end = int(parts[1])
            # Handle case where start > end? Usually assume normal range.
            return start, abs(end - start) + 1
        except: return -1, -1
    try:
        start = int(s)
        return start, 1
    except: return -1, -1

def _process_did_rows(rows: List[tuple], headers: List[str], result: Dict[str, Any]) -> None:
    norm_headers = [str(h).replace("\\n", " ").replace("\\r", "").strip().lower() if h else "" for h in headers]
    col_map = {}

    # Priority mapping
    # 1. Try to find explicit DID Number column
    for idx, h in enumerate(norm_headers):
        if h in ["did number", "did_number", "did identifier", "did_identifier", "did", "标识符", "did号"]:
            col_map["did"] = idx
            break

    # 2. If not found, try fuzzy match
    if "did" not in col_map:
        for idx, h in enumerate(norm_headers):
            # Check for DID column
            # Must contain "did" AND ("number" or "id")
            # BUT must NOT contain "desc" (to avoid DID Description)
            # AND must NOT contain "type" (to avoid DID Type)
            if "did" in h and ("number" in h or "id" in h) and "desc" not in h and "type" not in h:
                col_map["did"] = idx
            elif "did" not in col_map and h in ["identifier", "id", "routineid", "routine id", "标识符"]:
                col_map["did"] = idx

    if "did" not in col_map:
        return

    # Continue mapping other columns
    enc_idx = -1
    # 1. Look for explicit "Encoding" in headers (EN/CN)
    for idx, h in enumerate(norm_headers):
        if "encoding" in h or "编码" in h:
            enc_idx = idx
            break

    # 2. Look for "Data Type" if Encoding not found
    if enc_idx == -1:
        for idx, h in enumerate(norm_headers):
            if "data type" in h or "数据类型" in h:
                enc_idx = idx
                break

    # 3. Look for "Type" (generic)
    if enc_idx == -1:
        for idx, h in enumerate(norm_headers):
            if ("type" in h or "类型" in h) and "access" not in h: # ensure not Access Type
                enc_idx = idx
                break

    # 4. Look for "Format" (Last resort, often ambiguous)
    if enc_idx == -1:
        for idx, h in enumerate(norm_headers):
            if "format" in h or "格式" in h:
                enc_idx = idx
                break

    if enc_idx != -1:
        col_map["encoding"] = enc_idx

    for idx, h in enumerate(norm_headers):
        # Description: Capture both EN and CN
        if "did description(e)" in h or "description(e)" in h: col_map["desc_en"] = idx
        if "did description(c)" in h or "description(c)" in h: col_map["desc_cn"] = idx

        # Fallback for generic description
        if "desc_en" not in col_map and "desc_cn" not in col_map:
            if "desc" not in col_map and ("did description" in h or "description" in h or "name" in h or "desc" in h or "描述" in h or "名称" in h):
                col_map["desc"] = idx

        if "byte" in h or "offset" in h or "position" in h or "字节" in h or "偏移" in h: col_map["byte"] = idx
        if "bit" in h or "位" in h: col_map["bit"] = idx
        if "length" in h or "size" in h or "len" == h or "长度" in h: col_map["len"] = idx

        # Encoding already handled above with priority

        # Conversion: Support EN and CN
        if "conversion(e)" in h: col_map["conversion_en"] = idx
        if "conversion(c)" in h: col_map["conversion_cn"] = idx

        # Fallback for generic conversion
        if "conversion_en" not in col_map and "conversion_cn" not in col_map:
            if "conversion" not in col_map and ("conversion" in h or "scaling" in h or "factor" in h or "转换" in h or "关系" in h):
                col_map["conversion"] = idx

        # Sub Name: Capture both EN and CN
        if "sub data name(e)" in h or "data name(e)" in h: col_map["sub_name_en"] = idx
        if "sub data name(c)" in h or "data name(c)" in h: col_map["sub_name_cn"] = idx

        if "sub_name_en" not in col_map and "sub_name_cn" not in col_map:
            if "sub_name" not in col_map and ("sub data name" in h or "data name" in h or "子名称" in h): col_map["sub_name"] = idx

    current_did = None
    current_fields = []
    current_meta = {}
    current_did_len = 0

    def register_current():
        nonlocal current_did, current_fields, current_meta
        if current_did and current_fields:
            did_key = current_did.strip().upper().replace("0X", "")
            # Sort fields by offset
            current_fields.sort(key=lambda x: x.get("byte_offset", 0))
            result["parsers"][did_key] = {
                "config": {"fields": current_fields},
                "meta": current_meta
            }

    for row in rows:
        did_val = row[col_map["did"]] if "did" in col_map and col_map["did"] < len(row) else None

        # Check if new DID
        if did_val:
            did_str = str(did_val).strip()
            if did_str and did_str.lower() != "none":
                # Check if same DID to avoid resetting
                new_key = did_str.upper().replace("0X", "")
                curr_key = current_did.upper().replace("0X", "") if current_did else ""

                if new_key != curr_key:
                    register_current()

                    current_did = did_str
                    current_fields = []
                    current_meta = {}
                    current_did_len = 0

                # Extract Description (Merge EN and CN)
                desc_str = ""
                if "desc_en" in col_map and col_map["desc_en"] < len(row) and row[col_map["desc_en"]]:
                    desc_str += str(row[col_map["desc_en"]]).strip()
                if "desc_cn" in col_map and col_map["desc_cn"] < len(row) and row[col_map["desc_cn"]]:
                    cn_text = str(row[col_map["desc_cn"]]).strip()
                    if cn_text:
                        desc_str = f"{desc_str}({cn_text})" if desc_str else cn_text

                if not desc_str and "desc" in col_map and col_map["desc"] < len(row) and row[col_map["desc"]]:
                    desc_str = str(row[col_map["desc"]]).strip()

                if desc_str:
                    current_meta["description"] = desc_str

                if "len" in col_map and col_map["len"] < len(row):
                    try: current_did_len = int(row[col_map["len"]])
                    except: pass

        if current_did:
            field = {}

            # Name (Merge EN and CN)
            name_str = ""
            if "sub_name_en" in col_map and col_map["sub_name_en"] < len(row) and row[col_map["sub_name_en"]]:
                name_str += str(row[col_map["sub_name_en"]]).strip()
            if "sub_name_cn" in col_map and col_map["sub_name_cn"] < len(row) and row[col_map["sub_name_cn"]]:
                cn_text = str(row[col_map["sub_name_cn"]]).strip()
                if cn_text:
                    name_str = f"{name_str}({cn_text})" if name_str else cn_text

            if not name_str and "sub_name" in col_map and col_map["sub_name"] < len(row) and row[col_map["sub_name"]]:
                name_str = str(row[col_map["sub_name"]]).strip()

            if name_str:
                field["description"] = name_str

            if "description" not in field:
                # Fallback to metadata description logic
                desc_str = ""
                if "desc_en" in col_map and col_map["desc_en"] < len(row) and row[col_map["desc_en"]]:
                    desc_str += str(row[col_map["desc_en"]]).strip()
                if "desc_cn" in col_map and col_map["desc_cn"] < len(row) and row[col_map["desc_cn"]]:
                    cn_text = str(row[col_map["desc_cn"]]).strip()
                    if cn_text:
                         desc_str = f"{desc_str}({cn_text})" if desc_str else cn_text

                if not desc_str and "desc" in col_map and col_map["desc"] < len(row) and row[col_map["desc"]]:
                    desc_str = str(row[col_map["desc"]]).strip()

                if desc_str: field["description"] = desc_str

            # Bit Fields (Extract early for Byte Offset inference)
            bit_val = None
            if "bit" in col_map and col_map["bit"] < len(row):
                bit_raw = row[col_map["bit"]]
                # Fix: Explicitly check for None to handle integer 0 correctly (which evaluates to False)
                if bit_raw is not None and str(bit_raw).strip() != "" and str(bit_raw).lower() != "all":
                     bit_val = str(bit_raw).strip()

            # Encoding (Extract early for Bit/Byte inference)
            encoding_found = False
            if "encoding" in col_map and col_map["encoding"] < len(row):
                val = row[col_map["encoding"]]
                if val:
                    s = str(val).strip()
                    if s and s.lower() != "none":
                        field["encoding"] = s
                        encoding_found = True

            # Disabled inheritance based on user requirement: "每一行都不能继承"
            if not encoding_found and current_fields:
                 pass
                 # Previous logic:
                 # Inherit from last field ONLY IF not a bit field row switching context
                 # if not bit_val:
                 #     last_field = current_fields[-1]
                 #     if "encoding" in last_field:
                 #         field["encoding"] = last_field["encoding"]

            # Default to Unsigned if not found (Important: do not default to ASCII)
            if "encoding" not in field:
                field["encoding"] = "Unsigned"


            # If Encoding is ASCII/String, ignore bit_val (treat as standard byte field)
            is_ascii_enc = False
            enc = field.get("encoding", "")
            if enc and ("ASCII" in enc.upper() or "STRING" in enc.upper()):
                is_ascii_enc = True

            # Byte Offset & Length
            byte_start, byte_len = -1, -1
            if "byte" in col_map and col_map["byte"] < len(row):
                byte_start, byte_len = _parse_range(row[col_map["byte"]])

            if byte_start == -1:
                if current_fields:
                    last_field = current_fields[-1]
                    last_offset = last_field.get("byte_offset", 0)
                    last_len = last_field.get("byte_length", 1)

                    if bit_val:
                        byte_start = last_offset
                        byte_len = last_len
                    else:
                        byte_start = last_offset + last_len
                        byte_len = 1
                else:
                    if current_did_len > 0:
                        byte_start = 0
                        byte_len = current_did_len
                    else:
                        byte_start = 0
                        byte_len = 1

            field["byte_offset"] = byte_start
            field["byte_length"] = byte_len

            # Conversion Extraction Helper
            def parse_conv_str(s):
                s = str(s).strip()
                if not s or s.lower() == "none":
                    return None

                if s.startswith("{"):
                    try: return json.loads(s)
                    except: pass

                # Check for Linear Scaling
                if "resolution" in s.lower() or "offset" in s.lower():
                     lin_dict = {"type": "linear", "resolution": 1.0, "offset": 0.0}
                     # Handle formatting where lines might be separated by \n or real newlines or semicolons
                     # Normalize separators to newline
                     normalized = s.replace("\\r", "").replace("\\n", "\n").replace(";", "\n")
                     for line in normalized.split("\n"):
                         if "=" in line:
                            parts = line.split("=", 1)
                            k, v = parts[0].strip().lower(), parts[1].strip()
                            try:
                                if "resolution" in k: lin_dict["resolution"] = float(v)
                                elif "offset" in k: lin_dict["offset"] = float(v)
                            except: pass
                     return lin_dict

                # Check for Enum (0x00=Desc or 1=Desc)
                if "=" in s:
                    conv_dict = {}
                    valid_enum = False
                    normalized = s.replace("\\r", "").replace("\\n", "\n").replace(";", "\n").replace(",", "\n")
                    for line in normalized.split("\n"):
                         line = line.strip()
                         if not line: continue
                         if "=" in line:
                            parts = line.split("=", 1)
                            k, v = parts[0].strip().lower(), parts[1].strip()
                            # Strip quotes if present
                            v = v.strip('"').strip("'")
                            if k.startswith("0x"):
                                try: conv_dict[str(int(k, 16))] = v; valid_enum = True
                                except: pass
                            else:
                                try: conv_dict[str(int(k))] = v; valid_enum = True
                                except: pass
                    if valid_enum and conv_dict:
                        return conv_dict

                return s

            # Extract Conversion(s)
            conv_en = None
            if "conversion_en" in col_map and col_map["conversion_en"] < len(row):
                val = row[col_map["conversion_en"]]
                if val: conv_en = parse_conv_str(str(val))

            conv_cn = None
            if "conversion_cn" in col_map and col_map["conversion_cn"] < len(row):
                val = row[col_map["conversion_cn"]]
                if val: conv_cn = parse_conv_str(str(val))

            if not conv_en and not conv_cn and "conversion" in col_map and col_map["conversion"] < len(row):
                val = row[col_map["conversion"]]
                if val: conv_en = parse_conv_str(str(val))

            final_conv = None
            if conv_en and conv_cn:
                 if isinstance(conv_en, dict) and isinstance(conv_cn, dict):
                       # Merge enums
                       merged = {}
                       keys = set(conv_en.keys()) | set(conv_cn.keys())
                       for k in keys:
                           v_en = conv_en.get(k, "")
                           v_cn = conv_cn.get(k, "")
                           if v_en and v_cn: merged[k] = f"{v_en} ({v_cn})"
                           elif v_en: merged[k] = v_en
                           else: merged[k] = v_cn
                       final_conv = merged
                 elif isinstance(conv_en, str) and isinstance(conv_cn, str):
                       final_conv = f"{conv_en} ({conv_cn})"
                 else:
                       final_conv = conv_en
            elif conv_en:
                 final_conv = conv_en
            elif conv_cn:
                 final_conv = conv_cn

            if final_conv:
                field["conversion"] = final_conv

                # Removed heuristic ASCII promotion based on conversion string
                # User requirement: Strictly follow Encoding column.
                # If Encoding says ASCII, decode it. Else use conversion.
                # if isinstance(final_conv, str):
                #      if "ASCII" in final_conv.upper() or "STRING" in final_conv.upper():
                #          if not is_ascii_enc:
                #              is_ascii_enc = True
                #              field["encoding"] = "ASCII"
                #              bit_val = None # Reset bits if ASCII detected

            if not final_conv and current_fields:
                 pass
                 # Disabled inheritance based on user requirement
                 # Inherit conversion
                 # last_field = current_fields[-1]
                 # if "conversion" in last_field:
                 #     field["conversion"] = last_field["conversion"]

            # Logic to merge bit fields or add new field
            if bit_val:
                # User Requirement: "按照每行解析" (Parse per row).
                # Do NOT merge into existing field. Create a new field for every row.
                # This ensures 1 Excel Row = 1 Result Row, even for bits in the same byte.

                existing_field = None
                # Disabled merging logic below:
                # for f in current_fields:
                #     if f["byte_offset"] == byte_start and f["byte_length"] == byte_len:
                #         existing_field = f
                #         break

                if not existing_field:
                    existing_field = {
                        "description": f"Byte {byte_start}",
                        "byte_offset": byte_start,
                        "byte_length": byte_len,
                        "encoding": field.get("encoding", "Unsigned"),
                        "bit_fields": {}
                    }
                    current_fields.append(existing_field)

                # Add bit definition
                try:
                    # Handle "0~1" or "0-1" or "0"
                    is_range = False
                    b_start, b_end = -1, -1

                    if "~" in bit_val:
                        parts = bit_val.split("~")
                        b_start, b_end = int(parts[0]), int(parts[1])
                        is_range = True
                    elif "-" in bit_val:
                        parts = bit_val.split("-")
                        b_start, b_end = int(parts[0]), int(parts[1])
                        is_range = True

                    if is_range:
                        # Check if it covers the whole byte (0-7) for a 1-byte field
                        # This promotes it to a standard field to support ASCII/Encoding properly
                        if b_start == 0 and b_end == 7 and existing_field["byte_length"] == 1:
                             existing_field["description"] = field.get("description", existing_field["description"])
                             existing_field["encoding"] = field.get("encoding", existing_field["encoding"])
                             existing_field["conversion"] = field.get("conversion", existing_field["conversion"])
                             existing_field["bit_fields"] = {} # Clear bits to treat as standard
                        else:
                            for b_idx in range(b_start, b_end + 1):
                                 existing_field["bit_fields"][f"bit_{b_idx}"] = {
                                    "description": field.get("description", ""),
                                    "conversion": field.get("conversion")
                                }
                    else:
                        b_idx = int(bit_val)
                        existing_field["bit_fields"][f"bit_{b_idx}"] = {
                            "description": field.get("description", ""),
                            "conversion": field.get("conversion")
                        }
                except:
                    pass
            else:
                # Standard field
                if "byte_offset" in field and "byte_length" in field:
                    current_fields.append(field)

    register_current()

def _process_dtc_rows(rows: List[tuple], headers: List[str], result: Dict[str, Any]) -> None:
    norm_headers = [str(h).replace("\n", " ").replace("\r", "").strip().lower() if h else "" for h in headers]
    col_map = {}

    for idx, h in enumerate(norm_headers):
        if "hex" in h and "uds" in h: col_map["code"] = idx
        elif "code" not in col_map and ("dtc" in h or "fault code" in h or "code" in h): col_map["code"] = idx

        if "meaning(e)" in h: col_map["desc"] = idx
        elif "desc" not in col_map and ("description" in h or "name" in h or "desc" in h or "meaning" in h): col_map["desc"] = idx

        if "status" in h or "state" in h: col_map["status"] = idx

    if "code" not in col_map:
        return

    for row in rows:
        if len(row) <= col_map["code"]: continue

        code_val = row[col_map["code"]]
        if not code_val: continue

        code_str = str(code_val).strip().upper()

        # Filter out header rows or invalid data
        if len(code_str) < 3: continue
        if "DISPLAY" in code_str or "HEX" in code_str: continue

        final_code = code_str

        # Try to see if there is a better hex code in the next column?
        # In the file: Col 2 is P-Code, Col 3 is Hex.
        if col_map["code"] == 2 and len(row) > 3:
             val_next = row[3]
             if val_next and isinstance(val_next, (int, str)):
                 s_next = str(val_next).strip().upper()
                 # Check if it looks like 6 digit hex
                 if len(s_next) == 6 and all(c in "0123456789ABCDEF" for c in s_next):
                     final_code = s_next

        desc = str(row[col_map["desc"]]) if "desc" in col_map and col_map["desc"] < len(row) else ""
        status = str(row[col_map["status"]]) if "status" in col_map and col_map["status"] < len(row) else ""

        result["dtcs"][final_code] = {
            "code": final_code,
            "description": desc,
            "status": status
        }

def _process_json_content(content: Dict[str, Any], result: Dict[str, Any]) -> None:
    if "parsers" in content and isinstance(content["parsers"], dict):
        result["parsers"].update(content["parsers"])

    if "dtcs" in content:
        if isinstance(content["dtcs"], dict):
            result["dtcs"].update(content["dtcs"])
        elif isinstance(content["dtcs"], list):
            _process_structured_dtcs(content["dtcs"], result)

    # Support flat structured format (Legacy)
    if "dids" in content:
        _process_structured_dids(content["dids"], result)

    # Support Sheet-based format
    if "sheets" in content and isinstance(content["sheets"], dict):
        for sheet_name, sheet_data in content["sheets"].items():
            if "dids" in sheet_data:
                _process_structured_dids(sheet_data["dids"], result, sheet_name=sheet_name)
            if "dtcs" in sheet_data:
                if isinstance(sheet_data["dtcs"], list):
                    _process_structured_dtcs(sheet_data["dtcs"], result)

def _process_structured_dtcs(dtc_list: List[Dict], result: Dict[str, Any]) -> None:
    for item in dtc_list:
        code = item.get("code")
        if not code: continue
        result["dtcs"][code] = item

def _process_structured_dids(did_list: List[Dict], result: Dict[str, Any], sheet_name: str = "") -> None:
    for did_entry in did_list:
        did_val = did_entry.get("did_number")
        if not did_val: continue

        did_key = str(did_val).strip().upper().replace("0X", "")

        # Use provided sheet_name or fallback to entry's sheet_name
        sheet = sheet_name if sheet_name else did_entry.get("sheet_name", "")

        # Merge Description
        desc_e = did_entry.get("description_e", "")
        desc_c = did_entry.get("description_c", "")
        desc = desc_e
        if desc_c:
             desc = f"{desc}({desc_c})" if desc else desc_c

        fields = []

        # Convert items to DPT fields
        # Note: The items are already separated. We need to handle byte offsets etc.
        # Logic similar to _process_did_rows but strictly following the structured item

        # Group items that belong to the same field (multi-bit fields or same byte)
        # But here items are row-based.

        # We need to reconstruct the "current_fields" logic from _process_did_rows
        # to handle bit fields merging into a byte field if needed, or keeping them separate.
        # The parser supports bit fields internally.

        current_did_len = 0 # Not provided in new structure explicitly, inferred from items?

        # Sort items by byte, then bit
        items = sorted(did_entry.get("items", []), key=lambda x: (
            _parse_range(x.get("byte"))[0] if _parse_range(x.get("byte"))[0] != -1 else 9999,
            _parse_range(x.get("bit"))[0] if x.get("bit") else -1
        ))

        # We need to map items to DPTFieldDef dicts
        for item in items:
             # Basic field props
             f_desc_e = item.get("sub_data_name_e", "")
             f_desc_c = item.get("sub_data_name_c", "")
             f_desc = f_desc_e
             if f_desc_c:
                  f_desc = f"{f_desc}({f_desc_c})" if f_desc else f_desc_c

             byte_val = item.get("byte")
             byte_start, byte_len = _parse_range(byte_val)
             if byte_start == -1:
                 # Handle "All" or missing?
                 # If missing, it's problematic if we don't have continuity.
                 # Assuming conversion tool put valid data or we check it.
                 byte_start = 0
                 byte_len = 1 # Default?

             encoding = item.get("encoding", "Unsigned")

             # Conversion parsing helper (copied/adapted from XLSX parser)
             def parse_conv_str(s):
                s = str(s).strip()
                if not s or s.lower() == "none":
                    return None
                if s.startswith("{"):
                    try: return json.loads(s)
                    except: pass
                # Check for Linear Scaling
                if "resolution" in s.lower() or "offset" in s.lower():
                     lin_dict = {"type": "linear", "resolution": 1.0, "offset": 0.0}
                     normalized = s.replace("\\r", "").replace("\\n", "\n").replace(";", "\n")
                     for line in normalized.split("\n"):
                         if "=" in line:
                            parts = line.split("=", 1)
                            k, v = parts[0].strip().lower(), parts[1].strip()
                            try:
                                if "resolution" in k: lin_dict["resolution"] = float(v)
                                elif "offset" in k: lin_dict["offset"] = float(v)
                            except: pass
                     return lin_dict
                # Check for Enum (0x00=Desc or 1=Desc)
                if "=" in s:
                    conv_dict = {}
                    valid_enum = False
                    normalized = s.replace("\\r", "").replace("\\n", "\n").replace(";", "\n").replace(",", "\n")
                    for line in normalized.split("\n"):
                         line = line.strip()
                         if not line: continue
                         if "=" in line:
                            parts = line.split("=", 1)
                            k, v = parts[0].strip().lower(), parts[1].strip()
                            v = v.strip('"').strip("'")
                            if k.startswith("0x"):
                                try: conv_dict[str(int(k, 16))] = v; valid_enum = True
                                except: pass
                            else:
                                try: conv_dict[str(int(k))] = v; valid_enum = True
                                except: pass
                    if valid_enum and conv_dict:
                        return conv_dict
                return s

             # Conversion
             conv_e_raw = item.get("conversion_e")
             conv_c_raw = item.get("conversion_c")

             conv_en = parse_conv_str(conv_e_raw) if conv_e_raw else None
             conv_cn = parse_conv_str(conv_c_raw) if conv_c_raw else None

             conv = None
             if conv_en and conv_cn:
                 if isinstance(conv_en, dict) and isinstance(conv_cn, dict):
                       # Merge enums
                       merged = {}
                       keys = set(conv_en.keys()) | set(conv_cn.keys())
                       for k in keys:
                           v_en = conv_en.get(k, "")
                           v_cn = conv_cn.get(k, "")
                           if v_en and v_cn: merged[k] = f"{v_en} ({v_cn})"
                           elif v_en: merged[k] = v_en
                           else: merged[k] = v_cn
                       conv = merged
                 elif isinstance(conv_en, str) and isinstance(conv_cn, str):
                       conv = f"{conv_en} ({conv_cn})"
                 else:
                       conv = conv_en
             elif conv_en:
                 conv = conv_en
             elif conv_cn:
                 conv = conv_cn

             bit_val = item.get("bit")

             if bit_val and str(bit_val).lower() != "all":
                 # Bit Field
                 # Needs to be attached to a Byte Field
                 # Find or create existing byte field
                 target_field = None
                 for f in fields:
                     if f["byte_offset"] == byte_start and f.get("byte_length", 1) == byte_len:
                         target_field = f
                         break

                 if not target_field:
                     target_field = {
                         "description": f"Byte {byte_start}",
                         "byte_offset": byte_start,
                         "byte_length": byte_len,
                         "encoding": encoding,
                         "bit_fields": {}
                     }
                     fields.append(target_field)

                 # Ensure bit_fields exists
                 if "bit_fields" not in target_field:
                     target_field["bit_fields"] = {}

                 # Parse bit index
                 b_idx = str(bit_val)

                 is_range = False
                 b_start, b_end = -1, -1

                 if "~" in b_idx:
                      parts = b_idx.split("~")
                      try: b_start, b_end = int(parts[0]), int(parts[1]); is_range = True
                      except: pass
                 elif "-" in b_idx:
                      parts = b_idx.split("-")
                      try: b_start, b_end = int(parts[0]), int(parts[1]); is_range = True
                      except: pass

                 if is_range:
                      # If range is 0-7, promote to standard field if it's a single byte
                      if b_start == 0 and b_end == 7 and target_field["byte_length"] == 1:
                           target_field["description"] = f_desc
                           target_field["conversion"] = conv
                           target_field["bit_fields"] = {} # Clear bits
                      else:
                           for idx in range(b_start, b_end + 1):
                                target_field["bit_fields"][f"bit_{idx}"] = {
                                    "description": f_desc,
                                    "conversion": conv
                                }
                 else:
                      try:
                          idx = int(b_idx)
                          target_field["bit_fields"][f"bit_{idx}"] = {
                              "description": f_desc,
                              "conversion": conv
                          }
                      except: pass
             else:
                 # Standard Field
                 fields.append({
                     "description": f_desc,
                     "byte_offset": byte_start,
                     "byte_length": byte_len,
                     "encoding": encoding,
                     "conversion": conv
                 })

        result["parsers"][did_key] = {
            "config": {"fields": fields},
            "meta": {"description": desc, "category": sheet} # Store category
        }

def _parse_dpt_file_task(path_str: str) -> Dict[str, Any]:
    """
    Executed in a separate process.
    """
    import json
    # import openpyxl # Removed
    from pathlib import Path
    from app.common.utils.crypto_utils import dpt_encryptor

    path = Path(path_str)
    result = {"parsers": {}, "dtcs": {}, "default_parser_config": None}

    try:
        content_str = ""
        success = False

        # 1. Try reading as plain JSON (Legacy or unencrypted)
        try:
             # Only if extension suggests or just try
             if path.suffix.lower() == ".json":
                 content_str = path.read_text(encoding="utf-8").strip()
                 success = True
        except: pass

        # 2. Try reading as Encrypted (Priority)
        error_details = ""
        if not success:
            try:
                data_bytes = path.read_bytes()
                content_str = dpt_encryptor.decrypt(data_bytes)
                success = True
            except Exception as e:
                import traceback
                error_details = f"Decryption error: {str(e)}\n{traceback.format_exc()}"

        if success and content_str:
            try:
                content = json.loads(content_str)
                _process_json_content(content, result)
            except Exception as e:
                 return {"error": f"JSON Parse Error: {e}"}
        else:
            return {"error": f"Failed to load or decrypt DPT file: {path.name}. {error_details}"}

    except Exception as e:
        return {"error": str(e)}

    return result

# --- End Helper functions ---

class DPTService:
    """Manage loading and parsing of DPT definition files."""

    def __init__(self) -> None:
        self._config_service = di_container.resolve(AppConfigurationService)
        if not self._config_service:
            self._config_service = AppConfigurationService()
            di_container.register_singleton(AppConfigurationService, self._config_service)

        self._parser: Optional[DPTParser] = None
        self._parsers: dict[str, DPTParser] = {}
        self._did_metadata: dict[str, dict] = {}
        self._dtc_map: dict[str, dict] = {}
        self._current_path: Optional[str] = None
        self._loading = False
        self._status_callbacks = []

        # Load from config
        dpt_file = self._config_service.doip_settings.get("dpt_file")
        if dpt_file:
            self.load_from_file(dpt_file, persist=False)

    def add_status_callback(self, callback):
        """Add a callback for status updates. Callback signature: cb(status: str, message: str)"""
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)

    def remove_status_callback(self, callback):
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    def _notify_status(self, status: str, message: str = ""):
        for cb in self._status_callbacks:
            try:
                cb(status, message)
            except Exception:
                pass

    def _reset_state(self):
        self._parser = None
        self._parsers = {}
        self._did_metadata = {}
        self._dtc_map = {}
        self._current_path = None

    def load_from_file(self, file_path: str, persist: bool = True) -> None:
        path = Path(file_path).expanduser()
        if not path.exists():
            # Don't raise here if called from init, just print
            print(f"DPT file not found: {path}")
            return

        if persist:
            settings = self._config_service.doip_settings
            settings["dpt_file"] = str(path)
            self._config_service.doip_settings = settings

        # Check if already loading same file
        if self._loading and self._current_path == str(path):
            return

        # Start loading in thread
        t = threading.Thread(target=self._load_worker, args=(path,), daemon=True)
        t.start()

    def _load_worker(self, path: Path):
        self._loading = True
        self._notify_status("loading", f"正在从 {path.name} 加载 DPT...")
        try:
            data = None
            # Try multiprocessing first
            try:
                # Run parsing in separate process to avoid GIL blocking
                with ProcessPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_parse_dpt_file_task, str(path))
                    # This blocks the worker thread but releases GIL for main thread
                    data = future.result()
            except Exception as e:
                print(f"ProcessPoolExecutor failed, falling back to in-thread loading: {e}")
                self._load_chunked_fallback(path)
                return

            if "error" in data:
                raise Exception(data["error"])

            self._reset_state()

            # 1. Handle default parser
            if data.get("default_parser_config"):
                try:
                    self._parser = DPTParser.from_dict_config(data["default_parser_config"])
                except Exception as e:
                    print(f"Error creating default parser: {e}")

            # 2. Handle specific parsers with time slicing
            parsers_data = data.get("parsers", {})

            # We process items in small batches to ensure UI responsiveness
            start_time = time.time()

            for did_key, info in parsers_data.items():
                # Time slicing: if we've worked for > 15ms, sleep for 5ms
                if time.time() - start_time > 0.015:
                    time.sleep(0.005)
                    start_time = time.time()

                try:
                    parser = DPTParser.from_dict_config(info["config"])
                    if "description" in info["meta"]:
                        parser.description = info["meta"]["description"]

                    self._parsers[did_key] = parser
                    self._did_metadata[did_key] = info["meta"]
                except Exception:
                    pass

            # 3. Handle DTCs
            self._dtc_map = data.get("dtcs", {})

            self._current_path = str(path)
            self._notify_status("completed", "DPT 加载成功")
        except Exception as e:
            print(f"Error loading DPT file: {e}")
            self._reset_state()
            self._notify_status("error", f"加载 DPT 出错: {e}")
        finally:
            self._loading = False

    def _load_chunked_fallback(self, path: Path):
        try:
            suffix = path.suffix.lower()
            if suffix == ".json":
                self._load_chunked_json(path)
            elif suffix == ".xlsx":
                self._load_chunked_xlsx(path)
            # Support encrypted dat or generic fallback
            else:
                try:
                    self._load_chunked_encrypted(path)
                except Exception:
                    self._notify_status("error", f"Unsupported file extension or decryption failed: {suffix}")
                    return

            self._current_path = str(path)
            self._notify_status("completed", "DPT 加载成功")
        except Exception as e:
            print(f"Error loading DPT file (chunked): {e}")
            self._reset_state()
            self._notify_status("error", f"加载 DPT 出错: {e}")

    def _load_chunked_encrypted(self, path: Path) -> None:
        from app.common.utils.crypto_utils import dpt_encryptor
        try:
             data_bytes = path.read_bytes()
             content_str = dpt_encryptor.decrypt(data_bytes)
             data = json.loads(content_str)
        except Exception as e:
             raise Exception(f"Decryption failed: {e}")

        self._reset_state()
        result = {"parsers": {}, "dtcs": {}}
        _process_json_content(data, result)

        # Populate self
        self._parsers = {}
        self._did_metadata = {}
        self._dtc_map = result.get("dtcs", {})

        parsers_data = result.get("parsers", {})

        for did_key, info in parsers_data.items():
            try:
                parser = DPTParser.from_dict_config(info["config"])
                if "description" in info["meta"]:
                    parser.description = info["meta"]["description"]
                self._parsers[did_key] = parser
                self._did_metadata[did_key] = info["meta"]
            except Exception:
                pass


    def _load_chunked_json(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unsupported DPT format in {path}") from exc

        self._reset_state()

        if isinstance(data, list):
            self._parser = DPTParser.from_dict_config({"fields": data})
        elif isinstance(data, dict):
            if "fields" in data:
                self._parser = DPTParser.from_dict_config(data)
            else:
                for i, (key, value) in enumerate(data.items()):
                    if i % 20 == 0:
                        time.sleep(0.001)

                    did_key = key.strip().upper().replace("0X", "")
                    if isinstance(value, list):
                        config = {"fields": value}
                        meta = {}
                    elif isinstance(value, dict):
                        config = value.get("data_format", value)
                        meta = {
                            "diagnostic_session": value.get("diagnostic_session"),
                            "security_access": value.get("security_access"),
                            "description": value.get("description"),
                        }
                    else:
                        continue

                    try:
                        parser = DPTParser.from_dict_config(config)
                        if "description" in meta:
                            parser.description = meta["description"]
                        self._parsers[did_key] = parser
                        self._did_metadata[did_key] = meta
                    except Exception:
                        pass

    def _load_chunked_xlsx(self, path: Path) -> None:
        try:
            import openpyxl
        except ImportError:
            print("openpyxl is required to load .xlsx files")
            return

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        self._reset_state()

        try:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows_iter = ws.iter_rows(values_only=True)
                try:
                    headers_row = next(rows_iter)
                except StopIteration:
                    continue

                headers = [str(h).strip().lower() if h else "" for h in headers_row]
                is_did = any(k in headers for k in ["did", "identifier", "id"])
                is_dtc = any(k in headers for k in ["dtc", "code", "fault code"])

                if is_did:
                    self._parse_did_sheet_chunked(rows_iter, headers)
                elif is_dtc:
                    self._parse_dtc_sheet_chunked(rows_iter, headers)
        finally:
            wb.close()

    def _parse_did_sheet_chunked(self, rows_iterator, headers: List[str]):
        norm_headers = [str(h).replace("\n", " ").replace("\r", "").strip().lower() if h else "" for h in headers]
        col_map = {}

        # Priority mapping
        # 1. Try to find explicit DID Number column
        for idx, h in enumerate(norm_headers):
            if h in ["did number", "did_number", "did identifier", "did_identifier", "did"]:
                col_map["did"] = idx
                break

        # 2. If not found, try fuzzy match
        if "did" not in col_map:
            for idx, h in enumerate(norm_headers):
                # Check for DID column
                # Must contain "did" AND ("number" or "id")
                # BUT must NOT contain "desc" (to avoid DID Description)
                # AND must NOT contain "type" (to avoid DID Type)
                if "did" in h and ("number" in h or "id" in h) and "desc" not in h and "type" not in h:
                    col_map["did"] = idx
                elif "did" not in col_map and h in ["identifier", "id", "routineid", "routine id"]:
                    col_map["did"] = idx

        for idx, h in enumerate(norm_headers):
            # Description: Capture both EN and CN
            if "did description(e)" in h or "description(e)" in h: col_map["desc_en"] = idx
            if "did description(c)" in h or "description(c)" in h: col_map["desc_cn"] = idx

            # Fallback for generic description
            if "desc_en" not in col_map and "desc_cn" not in col_map:
                if "desc" not in col_map and ("did description" in h or "description" in h or "name" in h or "desc" in h):
                    # Avoid confusing with sub data name
                    if "sub" not in h:
                        col_map["desc"] = idx

            if "byte" in h or "offset" in h or "position" in h: col_map["byte"] = idx
            if "bit" in h: col_map["bit"] = idx
            if "length" in h or "size" in h or "len" == h: col_map["len"] = idx
            if "encoding" in h or "type" in h or "format" in h: col_map["encoding"] = idx

            # Conversion: Prefer English
            if "conversion(e)" in h: col_map["conversion"] = idx
            elif "conversion" not in col_map and ("conversion" in h or "scaling" in h or "factor" in h): col_map["conversion"] = idx

            # Sub Name: Capture both EN and CN
            if "sub data name(e)" in h or "data name(e)" in h: col_map["sub_name_en"] = idx
            if "sub data name(c)" in h or "data name(c)" in h: col_map["sub_name_cn"] = idx

            if "sub_name_en" not in col_map and "sub_name_cn" not in col_map:
                if "sub_name" not in col_map and ("sub data name" in h or "data name" in h): col_map["sub_name"] = idx

        if "did" not in col_map:
            return

        current_did = None
        current_fields = []
        current_meta = {}
        current_did_len = 0

        for i, row in enumerate(rows_iterator):
            if i % 20 == 0:
                time.sleep(0.001)

            did_val = row[col_map["did"]] if "did" in col_map and col_map["did"] < len(row) else None

            if did_val:
                did_str = str(did_val).strip()
                if did_str and did_str.lower() != "none":
                    # Check if same DID to avoid resetting
                    new_key = did_str.upper().replace("0X", "")
                    curr_key = current_did.upper().replace("0X", "") if current_did else ""

                    if new_key != curr_key:
                        if current_did and current_fields:
                            # Sort fields by offset
                            current_fields.sort(key=lambda x: x.get("byte_offset", 0))
                            self._register_did_parser(current_did, current_fields, current_meta)

                        current_did = did_str
                        current_fields = []
                        current_meta = {}
                        current_did_len = 0

                    # Extract Description
                    desc_str = ""
                    if "desc_en" in col_map and col_map["desc_en"] < len(row) and row[col_map["desc_en"]]:
                        desc_str += str(row[col_map["desc_en"]]).strip()
                    if "desc_cn" in col_map and col_map["desc_cn"] < len(row) and row[col_map["desc_cn"]]:
                        cn_text = str(row[col_map["desc_cn"]]).strip()
                        if cn_text:
                            if desc_str:
                                desc_str += f"({cn_text})"
                            else:
                                desc_str = cn_text

                    if not desc_str and "desc" in col_map and col_map["desc"] < len(row) and row[col_map["desc"]]:
                        desc_str = str(row[col_map["desc"]]).strip()

                    if desc_str:
                        current_meta["description"] = desc_str

                    if "len" in col_map and col_map["len"] < len(row):
                        try: current_did_len = int(row[col_map["len"]])
                        except: pass

            if current_did:
                field = {}

                # Name
                name_str = ""
                if "sub_name_en" in col_map and col_map["sub_name_en"] < len(row) and row[col_map["sub_name_en"]]:
                    name_str += str(row[col_map["sub_name_en"]]).strip()
                if "sub_name_cn" in col_map and col_map["sub_name_cn"] < len(row) and row[col_map["sub_name_cn"]]:
                    cn_text = str(row[col_map["sub_name_cn"]]).strip()
                    if cn_text:
                        if name_str:
                            name_str += f"({cn_text})"
                        else:
                            name_str = cn_text

                if not name_str and "sub_name" in col_map and col_map["sub_name"] < len(row) and row[col_map["sub_name"]]:
                    name_str = str(row[col_map["sub_name"]]).strip()

                if name_str:
                    field["description"] = name_str

                if "description" not in field:
                    desc_str = ""
                    if "desc_en" in col_map and col_map["desc_en"] < len(row) and row[col_map["desc_en"]]:
                        desc_str += str(row[col_map["desc_en"]]).strip()
                    if "desc_cn" in col_map and col_map["desc_cn"] < len(row) and row[col_map["desc_cn"]]:
                        cn_text = str(row[col_map["desc_cn"]]).strip()
                        if cn_text:
                            if desc_str:
                                desc_str += f"({cn_text})"
                            else:
                                desc_str = cn_text

                    if not desc_str and "desc" in col_map and col_map["desc"] < len(row) and row[col_map["desc"]]:
                        desc_str = str(row[col_map["desc"]]).strip()

                    if desc_str: field["description"] = desc_str

                # Byte Offset & Length
                byte_start, byte_len = -1, -1
                if "byte" in col_map and col_map["byte"] < len(row):
                    byte_start, byte_len = _parse_range(row[col_map["byte"]])

                if byte_start == -1:
                    if current_did_len > 0:
                        byte_start = 0
                        byte_len = current_did_len
                    else:
                        byte_start = 0
                        byte_len = 1


                # Encoding (Extract early for Bit/Byte inference)
                encoding_found = False
                if "encoding" in col_map and col_map["encoding"] < len(row):
                    val = row[col_map["encoding"]]
                    if val:
                        s = str(val).strip()
                        if s and s.lower() != "none":
                            field["encoding"] = s
                            encoding_found = True

                if not encoding_found and current_fields:
                     # Inherit from last field
                     last_field = current_fields[-1]
                     if "encoding" in last_field:
                         field["encoding"] = last_field["encoding"]

                # Bit Fields (Extract early for Byte Offset inference)
                bit_val = None
                if "bit" in col_map and col_map["bit"] < len(row):
                    bit_raw = row[col_map["bit"]]
                    if bit_raw and str(bit_raw).lower() != "all":
                        bit_val = str(bit_raw).strip()

                # If Encoding is ASCII/String, ignore bit_val (treat as standard byte field)
                is_ascii_enc = False
                enc = field.get("encoding", "")
                if enc and ("ASCII" in enc.upper() or "STRING" in enc.upper()):
                    is_ascii_enc = True

                if not is_ascii_enc:
                    conv = field.get("conversion")
                    if isinstance(conv, str):
                        conv_upper = conv.upper()
                        if "ASCII" in conv_upper or "STRING" in conv_upper:
                            is_ascii_enc = True
                            # Promote to encoding for consistency and inheritance
                            field["encoding"] = "ASCII"

                if is_ascii_enc:
                    bit_val = None

                # Byte Offset & Length
                byte_start, byte_len = -1, -1
                if "byte" in col_map and col_map["byte"] < len(row):
                    byte_start, byte_len = _parse_range(row[col_map["byte"]])

                if byte_start == -1:
                    # "All" or invalid or empty
                    # Try to infer from previous field
                    if current_fields:
                        last_field = current_fields[-1]
                        last_offset = last_field.get("byte_offset", 0)
                        last_len = last_field.get("byte_length", 1)

                        if bit_val:
                            # If it's a bit field and byte is unspecified, assume same byte as previous
                            byte_start = last_offset
                            byte_len = last_len
                        else:
                            # If it's a standard field and byte is unspecified, assume next byte
                            byte_start = last_offset + last_len
                            byte_len = 1
                    else:
                        # First field
                        if current_did_len > 0:
                            byte_start = 0
                            byte_len = current_did_len
                        else:
                            # Default to 0 if unknown
                            byte_start = 0
                            byte_len = 1 # Fallback

                field["byte_offset"] = byte_start
                field["byte_length"] = byte_len

                # Encoding (Already extracted)
                # ...

                # Conversion
                conversion_found = False
                if "conversion" in col_map and col_map["conversion"] < len(row):
                    conv_val = row[col_map["conversion"]]
                    if conv_val and str(conv_val).strip().lower() != "none":
                        conversion_found = True
                        try:
                            conv_str = str(conv_val).strip()
                            if conv_str.startswith("{"):
                                field["conversion"] = json.loads(conv_str)
                            elif "=" in conv_str:
                                # Check for Linear Scaling
                                if "Resolution" in conv_str or "Offset" in conv_str or "resolution" in conv_str.lower():
                                    # Parse Resolution/Offset
                                    lin_dict = {"type": "linear", "resolution": 1.0, "offset": 0.0}
                                    lines = conv_str.replace("\r", "").split("\n")
                                    for line in lines:
                                        if "=" in line:
                                            parts = line.split("=", 1)
                                            k = parts[0].strip().lower()
                                            v = parts[1].strip()
                                            try:
                                                if "resolution" in k:
                                                    lin_dict["resolution"] = float(v)
                                                elif "offset" in k:
                                                    lin_dict["offset"] = float(v)
                                            except: pass
                                    field["conversion"] = lin_dict
                                else:
                                    # Try to parse "0x00=Desc" format (Enum)
                                    conv_dict = {}
                                    lines = conv_str.replace("\r", "").split("\n")
                                    for line in lines:
                                        if "=" in line:
                                            parts = line.split("=", 1)
                                            key = parts[0].strip().lower()
                                            val = parts[1].strip()
                                            # Normalize key (remove 0x, handle integers)
                                            if key.startswith("0x"):
                                                try:
                                                    int_key = int(key, 16)
                                                    conv_dict[str(int_key)] = val
                                                except:
                                                    conv_dict[key] = val
                                            else:
                                                try:
                                                    int_key = int(key)
                                                    conv_dict[str(int_key)] = val
                                                except:
                                                    conv_dict[key] = val
                                    if conv_dict:
                                        field["conversion"] = conv_dict
                                    else:
                                        field["conversion"] = conv_str
                            else:
                                field["conversion"] = conv_str
                        except:
                            field["conversion"] = str(conv_val)

                if not conversion_found and current_fields:
                     # Inherit from last field
                     last_field = current_fields[-1]
                     if "conversion" in last_field:
                         field["conversion"] = last_field["conversion"]

                # Logic to merge bit fields or add new field
                if bit_val:
                    existing_field = None
                    for f in current_fields:
                        if f["byte_offset"] == byte_start and f["byte_length"] == byte_len:
                            existing_field = f
                            break

                    if not existing_field:
                        existing_field = {
                            "description": f"Byte {byte_start}",
                            "byte_offset": byte_start,
                            "byte_length": byte_len,
                            "encoding": field.get("encoding", "Unsigned"),
                            "bit_fields": {}
                        }
                        current_fields.append(existing_field)

                    try:
                        # Handle "0~1" or "0-1" or "0"
                        is_range = False
                        b_start, b_end = -1, -1

                        if "~" in bit_val:
                            parts = bit_val.split("~")
                            b_start, b_end = int(parts[0]), int(parts[1])
                            is_range = True
                        elif "-" in bit_val:
                            parts = bit_val.split("-")
                            b_start, b_end = int(parts[0]), int(parts[1])
                            is_range = True

                        if is_range:
                            # Check if it covers the whole byte (0-7) for a 1-byte field
                            # This promotes it to a standard field to support ASCII/Encoding properly
                            if b_start == 0 and b_end == 7 and existing_field["byte_length"] == 1:
                                 existing_field["description"] = field.get("description", existing_field["description"])
                                 existing_field["encoding"] = field.get("encoding", existing_field["encoding"])
                                 existing_field["conversion"] = field.get("conversion", existing_field["conversion"])
                                 existing_field["bit_fields"] = {} # Clear bits to treat as standard
                            else:
                                for b_idx in range(b_start, b_end + 1):
                                     existing_field["bit_fields"][f"bit_{b_idx}"] = {
                                    "description": field.get("description", ""),
                                    "conversion": field.get("conversion")
                                }
                    except:
                        pass
                else:
                    if "byte_offset" in field and "byte_length" in field:
                        current_fields.append(field)

        if current_did and current_fields:
            current_fields.sort(key=lambda x: x.get("byte_offset", 0))
            self._register_did_parser(current_did, current_fields, current_meta)

    def _parse_dtc_sheet_chunked(self, rows_iterator, headers: List[str]):
        norm_headers = [str(h).replace("\n", " ").replace("\r", "").strip().lower() if h else "" for h in headers]
        col_map = {}

        for idx, h in enumerate(norm_headers):
            if "hex" in h and "uds" in h: col_map["code"] = idx
            elif "code" not in col_map and ("dtc" in h or "fault code" in h or "code" in h): col_map["code"] = idx

            if "meaning(e)" in h: col_map["desc"] = idx
            elif "desc" not in col_map and ("description" in h or "name" in h or "desc" in h or "meaning" in h): col_map["desc"] = idx

            if "status" in h or "state" in h: col_map["status"] = idx

        if "code" not in col_map:
            return

        for i, row in enumerate(rows_iterator):
            if i % 20 == 0:
                time.sleep(0.001)

            if len(row) <= col_map["code"]: continue

            code_val = row[col_map["code"]]
            if not code_val: continue

            code_str = str(code_val).strip().upper()

            if len(code_str) < 3: continue
            if "DISPLAY" in code_str or "HEX" in code_str: continue

            final_code = code_str

            if col_map["code"] == 2 and len(row) > 3:
                 val_next = row[3]
                 if val_next and isinstance(val_next, (int, str)):
                     s_next = str(val_next).strip().upper()
                     if len(s_next) == 6 and all(c in "0123456789ABCDEF" for c in s_next):
                         final_code = s_next

            desc = str(row[col_map["desc"]]) if "desc" in col_map and col_map["desc"] < len(row) else ""
            status = str(row[col_map["status"]]) if "status" in col_map and col_map["status"] < len(row) else ""

            self._dtc_map[final_code] = {
                "code": final_code,
                "description": desc,
                "status": status
            }

    def _register_did_parser(self, did: str, fields: List[dict], meta: dict):
        did_key = did.strip().upper().replace("0X", "")
        self._did_metadata[did_key] = meta
        try:
            config = {"fields": fields}
            parser = DPTParser.from_dict_config(config)
            if "description" in meta:
                parser.description = meta["description"]
            self._parsers[did_key] = parser
        except Exception as e:
            print(f"Error creating parser for DID {did}: {e}")

    def is_ready(self) -> bool:
        return bool(self._parsers or self._parser or self._dtc_map)

    def get_parser(self, did: str) -> Optional[DPTParser]:
        did_key = did.strip().upper().replace("0X", "")
        return self._parsers.get(did_key)

    def parse_bytes(self, data: bytes, did: str = None) -> Optional[DPTParseResult]:
        if not did:
            if self._parser:
                return self._parser.parse_bytes(data)
            return None

        did_key = did.strip().upper().replace("0X", "")
        parser = self._parsers.get(did_key)
        if parser:
            # If data is empty/None, try to create dummy data of correct length to show structure
            if not data:
                # Calculate required length
                max_len = 0
                for f in parser._fields:
                    end = f.byte_offset + f.byte_length
                    if end > max_len: max_len = end
                if max_len > 0:
                    data = bytes([0] * max_len)
                else:
                    data = b''

            # Ensure data is long enough for the parser, otherwise pad it
            # (Optional: DPTParser handles short data by skipping fields, but for display we might want to show all)
            # Actually DPTParser skips if start >= len(data).
            # So padding is good for "Show Structure" feature

            max_len = 0
            for f in parser._fields:
                end = f.byte_offset + f.byte_length
                if end > max_len: max_len = end

            if len(data) < max_len:
                data = data + bytes([0] * (max_len - len(data)))

            return parser.parse_bytes(data)

        # Fallback
        if self._parser:
            return self._parser.parse_bytes(data)

        return None

    def get_did_data(self, did: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get the data structure (fields definition) for a specific DID.
        Returns a list of field definitions.
        """
        parser = self.get_parser(did)
        if not parser:
            return None

        # Convert internal DPTFieldDef objects back to dictionary format
        result = []
        for f in parser._fields:
            field_dict = {
                "description": f.name,
                "byte_offset": f.byte_offset,
                "byte_length": f.byte_length,
                "encoding": f.encoding,
                "conversion": f.conversion
            }
            if f.bit_fields:
                field_dict["bit_fields"] = f.bit_fields
            if f.fixed_value is not None:
                field_dict["fixed_value"] = f.fixed_value

            result.append(field_dict)

        return result

    def get_dtc_info(self, code: str) -> Optional[Dict[str, Any]]:
        """Get DTC information by code."""
        return self._dtc_map.get(code.strip().upper())
