import openpyxl
from typing import List, Dict, Any, Optional

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
            return start, abs(end - start) + 1
        except: return -1, -1
    try:
        start = int(s)
        return start, 1
    except: return -1, -1

def _find_col_idx(headers: List[str], keywords: List[str], exclude: List[str] = None) -> int:
    for idx, h in enumerate(headers):
        h_lower = h.lower()
        if any(k in h_lower for k in keywords):
            if exclude and any(e in h_lower for e in exclude):
                continue
            return idx
    return -1

def simple_row_get(row: tuple, idx: int) -> str:
    if 0 <= idx < len(row):
        val = row[idx]
        return str(val).strip() if val is not None else ""
    return ""

def _find_header_row_index(rows: List[tuple], max_scan=20) -> int:
    """Scans the first few rows to find the most likely header row."""
    for i in range(min(len(rows), max_scan)):
        row_values = [str(c).lower().strip() for c in rows[i] if c is not None]

        # Check for DID identifiers
        has_did = any(kw in row_values for kw in ["did number", "did identifier", "did", "rid", "routine identifier", "identifier"])
        # Check for DTC identifiers
        has_dtc = any(kw in row_values for kw in ["dtc", "fault code", "code", "dtc code"])

        # Check for common attributes to confirm it's a header row
        has_attr = any(kw in val for val in row_values for kw in ["description", "byte", "bit", "status", "name", "meaning", "conversion"])

        if (has_did or has_dtc) and has_attr:
            return i

    return 0

def parse_excel_to_json_structure(file_path: str) -> Dict[str, Any]:
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)

    sheets_data = {}

    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows: continue

            # Attempt to find the header row instead of assuming row 0
            header_idx = _find_header_row_index(rows)
            headers_raw = rows[header_idx]

            headers = [str(h).strip() if h else "" for h in headers_raw] # Keep original case for display? Lower for matching.
            headers_lower = [h.lower() for h in headers]

            s_name = sheet_name.lower()

            # Identify Sheet Type
            # User mentioned: "DID", "DTC", "19"
            is_did_sheet = "did" in s_name or "19" in s_name or "service" in s_name
            is_dtc_sheet = "dtc" in s_name

            if not is_did_sheet and not is_dtc_sheet:
                # Fallback heuristics
                if any(k in headers_lower for k in ["did number", "did_number", "did identifier", "rid", "wdid"]):
                     is_did_sheet = True
                elif any(k in headers_lower for k in ["dtc", "fault code"]):
                     is_dtc_sheet = True

            data_rows = rows[header_idx+1:]

            result_dids = []
            result_dtcs = []

            if is_did_sheet:
                _extract_did_sheet(data_rows, headers_lower, result_dids)
            elif is_dtc_sheet:
                _extract_dtc_sheet(data_rows, headers_lower, result_dtcs)

            if result_dids or result_dtcs:
                sheets_data[sheet_name] = {
                    "dids": result_dids,
                    "dtcs": result_dtcs
                }

    finally:
        wb.close()

    return {
        "sheets": sheets_data
    }

def _extract_did_sheet(rows: List[tuple], headers: List[str], result_list: List[Dict]):
    # Column Mapping
    col_map = {}

    # DID Number
    col_map["did_number"] = -1
    for idx, h in enumerate(headers):
        if h in ["did number", "did_number", "did identifier", "did", "标识符", "did号", "rid", "routine identifier", "id", "identifier", "no.", "no", "routineid", "routine id"]:
            col_map["did_number"] = idx
            break
    if col_map["did_number"] == -1:
        # Fuzzy
        for idx, h in enumerate(headers):
             if ("did" in h or "rid" in h or "routine" in h) and ("number" in h or "id" in h) and "desc" not in h:
                 col_map["did_number"] = idx; break

    if col_map["did_number"] == -1: return

    # Descriptions
    col_map["desc_en"] = _find_col_idx(headers, ["did description(e)", "description(e)"])
    col_map["desc_cn"] = _find_col_idx(headers, ["did description(c)", "description(c)"])

    # Sub Data Name
    col_map["sub_name_en"] = _find_col_idx(headers, ["sub data name(e)", "data name(e)"])
    col_map["sub_name_cn"] = _find_col_idx(headers, ["sub data name(c)", "data name(c)"])

    # Conversion
    col_map["conv_en"] = _find_col_idx(headers, ["conversion(e)"])
    col_map["conv_cn"] = _find_col_idx(headers, ["conversion(c)"])
    if col_map["conv_en"] == -1 and col_map["conv_cn"] == -1:
        # Fallback to generic conversion
        col_map["conv_en"] = _find_col_idx(headers, ["conversion", "scaling", "factor", "转换", "关系"])

    # Others
    # Exclude "length" to avoid matching "Length (Byte)" when looking for "Byte"
    col_map["byte"] = _find_col_idx(headers, ["byte", "offset", "position", "字节"], exclude=["length", "len", "size", "长度"])
    col_map["bit"] = _find_col_idx(headers, ["bit", "位"]) # Be careful of "bit" in "bit rate" etc but headers are usually specific
    col_map["encoding"] = _find_col_idx(headers, ["encoding", "type", "format", "编码", "类型"])

    # Processing state
    current_did_entry = None
    last_byte_val = None

    for row in rows:
        did_val = simple_row_get(row, col_map["did_number"])

        # Check if new DID
        if did_val and did_val.lower() != "none":
            # Start new DID
            desc_en = simple_row_get(row, col_map["desc_en"])
            desc_cn = simple_row_get(row, col_map["desc_cn"])

            # Create new entry
            current_did_entry = {
                "did_number": did_val,
                "description_e": desc_en,
                "description_c": desc_cn,
                "items": []
            }
            result_list.append(current_did_entry)
            last_byte_val = None # Reset for new DID

        # If we have a current DID, parse the row as a field item
        if current_did_entry is not None:
            # We add an item for every row that has field info

            sub_en = simple_row_get(row, col_map["sub_name_en"])
            sub_cn = simple_row_get(row, col_map["sub_name_cn"])
            byte_val = simple_row_get(row, col_map["byte"])
            bit_val = simple_row_get(row, col_map["bit"])
            enc_val = simple_row_get(row, col_map["encoding"])
            conv_en = simple_row_get(row, col_map["conv_en"])
            conv_cn = simple_row_get(row, col_map["conv_cn"])

            # Logic to inherit byte_val if empty
            if byte_val:
                last_byte_val = byte_val
            elif last_byte_val is not None:
                # If byte is empty but we have a previous one in this DID context, use it
                byte_val = last_byte_val

            # Only add if there is at least some field info
            if any([sub_en, sub_cn, byte_val, bit_val, enc_val, conv_en, conv_cn]):
                 current_did_entry["items"].append({
                     "byte": byte_val,
                     "bit": bit_val,
                     "sub_data_name_e": sub_en,
                     "sub_data_name_c": sub_cn,
                     "conversion_e": conv_en,
                     "conversion_c": conv_cn,
                     "encoding": enc_val
                 })

def _extract_dtc_sheet(rows: List[tuple], headers: List[str], result_list: List[Dict]):
    col_map = {}
    col_map["code"] = _find_col_idx(headers, ["dtc", "code", "fault code"])
    col_map["desc"] = _find_col_idx(headers, ["meaning(e)", "description", "name"]) # Assuming one description for DTC or E/C?
    # User didn't specify DTC columns in detail ("only need DID and DTC... and columns DID number...").
    # Actually user listed columns for DID specifically. For DTC, "and DTC ... related sheet pages".
    # Assuming standard DTC extraction.
    col_map["status"] = _find_col_idx(headers, ["status", "state"])

    if col_map["code"] == -1: return

    for row in rows:
        code = simple_row_get(row, col_map["code"])
        if not code or len(code) < 3: continue
        if "DISPLAY" in code.upper() or "HEX" in code.upper(): continue

        desc = simple_row_get(row, col_map["desc"])
        status = simple_row_get(row, col_map["status"])

        result_list.append({
            "code": code,
            "description": desc,
            "status": status
        })
