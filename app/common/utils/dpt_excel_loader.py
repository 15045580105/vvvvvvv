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

def _normalize_header(val: Any) -> str:
    if val is None: return ""
    s = str(val)
    # Replace newlines and tabs with space, then collapse multiple spaces
    return " ".join(s.split()).lower()

def _find_col_idx(headers: List[str], keywords: List[str], exclude: List[str] = None) -> int:
    for idx, h in enumerate(headers):
        # Already normalized headers expected, but re-normalizing doesn't hurt
        h_lower = h if h else ""
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
        row_values = [_normalize_header(c) for c in rows[i] if c is not None]

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
            headers_lower = [_normalize_header(h) for h in headers_raw]

            s_name = sheet_name.lower()

            # Identify Sheet Type
            # User mentioned: "DID", "DTC", "19"
            is_did_sheet = "did" in s_name or "19" in s_name or "service" in s_name or \
                           "22" in s_name or "2e" in s_name or "2f" in s_name or "31" in s_name
            is_dtc_sheet = "dtc" in s_name

            if not is_did_sheet and not is_dtc_sheet:
                # Fallback heuristics
                if any(k in headers_lower for k in ["did number", "did_number", "did identifier", "rid", "wdid", "identifier", "id"]):
                     is_did_sheet = True
                elif any(k in headers_lower for k in ["dtc", "fault code"]):
                     is_dtc_sheet = True
                # [NEW] Check for config columns if headers are ambiguous
                elif any(k in headers_lower for k in ["app support", "app_support", "flash software", "securitystate", "supported in securitystate"]):
                     is_did_sheet = True

            data_rows = rows[header_idx+1:]

            result_dids = []
            result_dtcs = []

            if is_did_sheet:
                _extract_did_sheet(rows, header_idx, result_dids)
            elif is_dtc_sheet:
                _extract_dtc_sheet(data_rows, headers_lower, result_dtcs)

            if result_dids or result_dtcs:
                sheet_obj = {}
                if result_dids:
                    sheet_obj["dids"] = result_dids
                if result_dtcs:
                    sheet_obj["dtcs"] = result_dtcs
                sheets_data[sheet_name] = sheet_obj

    finally:
        wb.close()

    return {
        "sheets": sheets_data
    }


def _extract_did_sheet(all_rows: List[tuple], header_idx: int, result_list: List[Dict]):
    # 1. Parsing Context
    # Locate Field Header Row (containing Byte, Bit) which might be deeper than header_idx + 1
    field_header_idx = -1
    max_scan = min(len(all_rows), header_idx + 6)

    # Keywords to identifying header row (Byte/Bit OR Configuration Columns)
    for r in range(header_idx, max_scan):
        r_vals = [_normalize_header(c) for c in all_rows[r]]

        has_byte_bit = (any(k in v for v in r_vals for k in ["byte", "offset", "position", "字节"]) and \
                        any(k in v for v in r_vals for k in ["bit", "位"]))

        if has_byte_bit:
             field_header_idx = r
             break

        if ("default" in r_vals and any(x in r_vals for x in ["extended", "exended", "programming"])):
             field_header_idx = r
             break

        if ("locked" in r_vals and any(x in r_vals for x in ["level 1", "level1", "level 3", "level3"])):
             field_header_idx = r
             break

    if field_header_idx == -1:
        # Fallback: check if header_idx + 1 looks like data or header
        if header_idx + 1 < len(all_rows):
             row_next = [_normalize_header(c) for c in all_rows[header_idx + 1]]
             # Heuristic: Data often contains "0", "1", "0x..", "yes/no", empty.
             # Headers often contain words.

             data_score = 0
             for v in row_next:
                 if v in ["0", "1", "o", "yes", "no", "true", "false", "nan", "none"] or v.startswith("0x") or v.isdigit():
                     data_score += 1

             if data_score > 2 or (len(row_next) > 4 and data_score >= 1):
                  field_header_idx = header_idx
             else:
                  field_header_idx = header_idx + 1
        else:
             field_header_idx = header_idx

    # [Revised] Check for separate Config Header Row (e.g. Row 1 has Default/Locked, Row 0 has Byte/Bit)
    config_header_idx = field_header_idx
    if field_header_idx + 1 < len(all_rows):
        next_r = [_normalize_header(c) for c in all_rows[field_header_idx + 1]]
        # Strong indicators for Config Row
        cfg_kws = ["default", "extended", "programming", "locked", "level1", "level 1", "level3", "level 3"]
        matches = sum(1 for v in next_r if any(k == v or k in v for k in cfg_kws))

        # Anti-indicators (Data)
        data_matches = sum(1 for v in next_r if v.isdigit() or "0x" in v or v in ["y", "n", "yes", "no"])

        if matches >= 2 and data_matches <= matches:
            config_header_idx = field_header_idx + 1

    headers0 = [_normalize_header(h) for h in all_rows[header_idx]]

    # We use explicit list for index matching later
    field_row_raw = all_rows[field_header_idx]
    field_row_lower = [_normalize_header(h) for h in field_row_raw]

    # 2. Identify DID Identifier/Description (Main Headers)
    did_idx = -1
    for idx, h in enumerate(headers0):
        if h in ["did number", "did_number", "did identifier", "did", "标识符", "did号", "rid", "routine identifier", "id", "identifier", "no.", "no", "routineid", "routine id", "routineid"]:
            did_idx = idx
            break
    if did_idx == -1:
        for idx, h in enumerate(headers0):
             if ("did" in h or "rid" in h or "routine" in h) and ("number" in h or "id" in h) and "desc" not in h:
                 did_idx = idx; break

    if did_idx == -1: return

    desc_en_idx = _find_col_idx(headers0, ["did description(e)", "description(e)"])
    desc_cn_idx = _find_col_idx(headers0, ["did description(c)", "description(c)"])
    if desc_en_idx == -1: desc_en_idx = _find_col_idx(headers0, ["rid description(e)", "rid description"], exclude=["(c)"])
    if desc_cn_idx == -1: desc_cn_idx = _find_col_idx(headers0, ["rid description(c)"])

    # 3. Identify Regions (Field Groups)
    regions = []

    # Prepare Group Names (Look at rows between header_idx and field_header_idx)
    group_stack = []
    if field_header_idx > header_idx:
        for r_idx in range(header_idx, field_header_idx):
            row_data = all_rows[r_idx]
            filled_row = []
            last_val = ""
            for cell in row_data:
                val = _normalize_header(cell)
                if val: last_val = val
                filled_row.append(last_val)
            group_stack.append(filled_row)

    # A. Byte-based Regions (Complex groups)
    byte_indices = []
    for idx, h in enumerate(field_row_lower):
        if ("byte" in h or "offset" in h or "position" in h or "字节" in h) and not any(x in h for x in ["length", "len", "size", "长度"]):
            byte_indices.append(idx)

    for b_idx in byte_indices:
        # Construct Group Name from stack
        curr_group_parts = []
        for gr in group_stack:
            if b_idx < len(gr) and gr[b_idx]:
                 val = gr[b_idx]
                 if val not in ["did number", "description", "byte", "bit", "位", "字节"]:
                     curr_group_parts.append(val)

        final_group_parts = []
        if curr_group_parts:
            final_group_parts.append(curr_group_parts[0])
            for p in curr_group_parts[1:]:
                if p != final_group_parts[-1]:
                    final_group_parts.append(p)

        group_name = " - ".join(final_group_parts) if final_group_parts else ""
        if not group_name and b_idx < len(headers0) and headers0[b_idx]:
             group_name = headers0[b_idx]

        # Determine Region End
        limit_idx = len(field_row_lower)
        for other_b in byte_indices:
            if other_b > b_idx:
                limit_idx = min(limit_idx, other_b)
                break

        def find_in_slice(keywords, start, end):
            for i in range(start, end):
                if i >= len(field_row_lower): break
                h = field_row_lower[i]
                if any(k in h for k in keywords):
                    return i
            return -1

        bit_idx = find_in_slice(["bit", "位"], b_idx, limit_idx)
        enc_idx = find_in_slice(["encoding", "type", "format", "编码", "类型"], b_idx, limit_idx)
        desc_e = find_in_slice(["sub data name(e)", "data name(e)", "description(e)"], b_idx, limit_idx)
        desc_c = find_in_slice(["sub data name(c)", "data name(c)", "description(c)"], b_idx, limit_idx)
        conv_e = find_in_slice(["conversion(e)"], b_idx, limit_idx)
        # Fix: Check raw content for conversion(c) to differentiate
        conv_c = find_in_slice(["conversion(c)"], b_idx, limit_idx)
        if conv_e == -1 and conv_c == -1:
            conv_e = find_in_slice(["conversion", "scaling", "factor", "转换", "关系"], b_idx, limit_idx)

        regions.append({
            "type": "complex",
            "group": group_name,
            "byte": b_idx,
            "bit": bit_idx,
            "encoding": enc_idx,
            "sub_name_e": desc_e,
            "sub_name_c": desc_c,
            "conv_e": conv_e,
            "conv_c": conv_c
        })

    # B. Specific Single-Column Regions (ONLY if not covered by Byte Regions)
    specific_col_names = ["inputoutputparameter", "routinecontroltype", "controloption", "sub function", "parameter", "routinecontroloption", "routinecontrolstatus", "controlstatus"]

    # Detect Mode Column (SubFunction / Parameter type) used for high-level grouping
    mode_col_keywords = ["routinecontroltype", "inputoutputparameter", "sub function"]
    mode_col_idx = -1
    for idx, h in enumerate(headers0):
        if any(k in h for k in mode_col_keywords):
            # Ensure it is not a byte region
            is_byte = False
            for r in regions:
                 if r.get("byte") == idx: is_byte = True; break
            if not is_byte:
                mode_col_idx = idx
                break

    for idx, h in enumerate(headers0):
        if any(k in h for k in specific_col_names):
             # Exclude Mode Column from being a parseable region
             if mode_col_idx != -1 and idx == mode_col_idx:
                 continue

             is_covered = False
             for r in regions:
                 # If a byte region starts at the same index, or if the index is within [byte, bit...]
                 if idx == r.get("byte"): is_covered = True

             if not is_covered:
                regions.append({
                    "type": "simple",
                    "group": headers0[idx],
                    "col_idx": idx
                })

    # [NEW] C. Identify Special Configuration Columns (Session/Security Support)
    config_cols = {}

    # Prepare Config Context
    config_row_lower = field_row_lower
    config_group_stack = group_stack

    if config_header_idx != field_header_idx:
        config_row_lower = [_normalize_header(h) for h in all_rows[config_header_idx]]
        config_group_stack = []
        for r_idx in range(header_idx, config_header_idx):
             row_data = all_rows[r_idx]
             filled_row = []
             last_val = ""
             for cell in row_data:
                 val = _normalize_header(cell)
                 if val: last_val = val
                 filled_row.append(last_val)
             config_group_stack.append(filled_row)

    target_configs = [
        # (Key, Sub-Keywords, Parent-Keywords)
        # Note: Sub-Keywords are checked against Current Column Header (Field Row).
        # Parent-Keywords are checked against context (Group Stack + Header 0).
        # If Parent-Keywords list contains entries that are also in Sub-Keywords (e.g. "default"),
        # it helps matching when the column header itself is descriptive enough (e.g. "Default Session")

        ("session_default", ["default", "std"], ["app support", "app_support", "default", "session", "diagnostic session"]),
        ("session_extended", ["extended", "exended", "ext"], ["app support", "app_support", "extended", "exended", "session", "diagnostic session"]),
        ("session_programming", ["programming", "prog", "flash"], ["flash software", "flash_software", "programming", "session", "diagnostic session", "boot", "boot support"]),
        ("security_locked", ["locked", "lock"], ["supported in securitystate", "securitystate", "security state", "locked", "lock", "security", "access"]),
        ("security_level1", ["level1", "level 1", "lev1", "l1"], ["supported in securitystate", "securitystate", "security state", "level1", "level 1", "security", "access"]),
        ("security_level2", ["level2", "level 2", "lev2", "l2"], ["supported in securitystate", "securitystate", "security state", "level2", "level 2", "security", "access"]),
        ("security_level3", ["level3", "level 3", "lev3", "l3"], ["supported in securitystate", "securitystate", "security state", "level3", "level 3", "security", "access"]),
        ("security_level_flash", ["level flash", "levelflash", "flash level"], ["supported in securitystate", "securitystate", "security state", "level flash", "levelflash", "security", "access"])
    ]

    # Use max width to ensure we don't miss headers that are wider than field_row
    max_cols = max(len(config_row_lower), len(headers0))
    if config_group_stack:
        for r in config_group_stack:
            max_cols = max(max_cols, len(r))

    for idx in range(max_cols):
         # Build context string list for this column
         col_context = []
         if config_group_stack:
              for grp_row in config_group_stack:
                   if idx < len(grp_row) and grp_row[idx]:
                        col_context.append(grp_row[idx])

         # Add header0 if distinct
         if idx < len(headers0) and headers0[idx]:
              if headers0[idx] not in col_context: col_context.append(headers0[idx])

         current_sub = config_row_lower[idx] if idx < len(config_row_lower) else ""

         # Skip columns that are clearly description or value definitions
         if any(x in current_sub for x in ["value", "值", "desc", "name", "content", "byte", "bit", "encoding"]):
              continue

         check_terms = [current_sub] + col_context

         for key, sub_kws, parent_kws in target_configs:
              if key in config_cols: continue

              # Separate checks for current header vs context
              match_sub = any(kw == current_sub or kw in current_sub for kw in sub_kws)

              if match_sub:
                  # Strong match on column name (e.g. "Programming")
                  if parent_kws:
                       # Optional validation against context if parent keywords exist
                       # But for column headers, we trust them highly.
                       # Only check parent if we want to distinguish same-named columns?
                       # For now, trust the sub match, but lets verify parent if it exists to be safe?
                       # No, direct match is usually enough.
                       pass
                  config_cols[key] = idx
                  break # Found a match for this column, move to next column? No, one col can be multiple things? Unlikely.

              else:
                  # No direct match on column name. Check context?
                  # Only allow context match if current_sub is NOT a strong keyword for OTHER categories.
                  # e.g. If current_sub is "Default", we should NOT match "session_programming" via context "Flash Software",
                  # because "Default" is a strong keyword for "session_default".

                  # Definition of "Generic" headers that allow context fallback
                  is_generic = not current_sub or any(g in current_sub for g in ["support", "status", "state", "value", "yy", "nn", "check", "byte", "bit"])

                  # Also fail if current_sub looks like a keyword for another known config type
                  # Simple heuristic: if it matches "default", "locked", "level", "extended", it's specific.
                  is_specific_other = any(k in current_sub for k in ["default", "locked", "level", "extended", "standard", "std", "programming"])

                  if not is_generic and is_specific_other:
                       continue

                  # Check context
                  context_match = False
                  if parent_kws:
                       # Parent keywords must be present in context
                       if any(any(p_kw in term for p_kw in parent_kws) for term in col_context):
                            # And at least one sub_kw (or parent_kw?) must be in context to justify the category?
                            # In original logic: ANY term in check_terms matches sub_kws.
                            # check_terms = [current_sub] + col_context.
                            # Since current_sub didn't match, we are checking if col_context matches sub_kws.
                            if any(any(kw in term for kw in sub_kws) for term in col_context):
                                 config_cols[key] = idx
                                 break
                       else:
                            # parent_kws defined but not found -> no match
                            pass
                  else:
                       # No parent kws defined, relying solely on sub_kws in context? Rare.
                       if any(any(kw in term for kw in sub_kws) for term in col_context):
                            config_cols[key] = idx
                            break

    # 4. Data Parsing
    data_start = max(field_header_idx, config_header_idx) + 1
    current_did_entry = None
    region_states = { i: {"last_byte": None} for i in range(len(regions)) }

    # Track current mode for merged cells
    current_mode = "Default"

    for row_idx in range(data_start, len(all_rows)):
        row = all_rows[row_idx]
        did_val = simple_row_get(row, did_idx)

        # Handle Mode (SubFunction) Value
        mode_val_raw = ""
        if mode_col_idx != -1:
            mode_val_raw = simple_row_get(row, mode_col_idx)

        if did_val and did_val.lower() != "none" and did_val.lower() != "nan":
             desc_en = simple_row_get(row, desc_en_idx)
             desc_cn = simple_row_get(row, desc_cn_idx)

             current_did_entry = {
                "did_number": did_val,
                "description_e": desc_en,
                "description_c": desc_cn,
             }

             # [NEW] Read Configuration Column Values
             all_config_keys = [
                 "session_default", "session_extended", "session_programming",
                 "security_locked", "security_level1", "security_level2",
                 "security_level3", "security_level_flash"
             ]

             for key in all_config_keys:
                 val = "-"
                 if key in config_cols:
                     v = simple_row_get(row, config_cols[key])
                     if v and str(v).lower() != "none" and str(v).lower() != "nan":
                         val = v
                 current_did_entry[key] = val

             if mode_col_idx != -1:
                 current_did_entry["modes"] = {}
             else:
                 current_did_entry["items"] = []

             result_list.append(current_did_entry)
             for k in region_states: region_states[k]["last_byte"] = None

             current_mode = "Default"
             if mode_val_raw:
                 current_mode = mode_val_raw

        # Update mode if not new DID but mode changed
        if not did_val and mode_val_raw:
            current_mode = mode_val_raw

        if current_did_entry:
            if mode_col_idx != -1:
                # Ensure mode dict exists for hierarchical Structure
                if current_mode not in current_did_entry["modes"]:
                    current_did_entry["modes"][current_mode] = {}

            for r_idx, region in enumerate(regions):
                item = None
                grp_name = region["group"]

                if region["type"] == "complex":
                    byte_val = simple_row_get(row, region["byte"])
                    # Inherit byte
                    if not byte_val and region_states[r_idx]["last_byte"]:
                        # Only inherit if there is bit or sub-desc content
                        if simple_row_get(row, region["bit"]) or simple_row_get(row, region["sub_name_e"]):
                             byte_val = region_states[r_idx]["last_byte"]

                    if byte_val:
                        region_states[r_idx]["last_byte"] = byte_val

                        bit_val = simple_row_get(row, region["bit"])
                        enc_val = simple_row_get(row, region["encoding"])
                        sub_en = simple_row_get(row, region["sub_name_e"])
                        sub_cn = simple_row_get(row, region["sub_name_c"])
                        conv_en = simple_row_get(row, region["conv_e"])
                        conv_cn = simple_row_get(row, region["conv_c"])

                        if any([bit_val, sub_en, sub_cn, enc_val, conv_en]):
                            item = {
                                "byte": byte_val,
                                "bit": bit_val,
                                "sub_data_name_e": sub_en,
                                "sub_data_name_c": sub_cn,
                                "conversion_e": conv_en,
                                "conversion_c": conv_cn,
                                "encoding": enc_val
                            }
                            # Group is handled by hierarchy or preserved below

                elif region["type"] == "simple":
                    val = simple_row_get(row, region["col_idx"])
                    if val and val.lower() != "none":
                        item = {
                            "byte": "",
                            "bit": "",
                            "sub_data_name_e": grp_name,
                            "sub_data_name_c": "",
                            "conversion_e": val,
                            "conversion_c": "",
                            "encoding": "Hex" if "0x" in val else "String"
                        }
                        if "0x" in val or val.isdigit():
                             item["fixed_value"] = val
                             item["conversion_e"] = ""

                if item:
                    # Add to structure
                    if mode_col_idx != -1:
                        # Hierarchical Mode
                        if "group" in item: del item["group"]

                        final_grp = grp_name or "General"
                        if final_grp not in current_did_entry["modes"][current_mode]:
                            current_did_entry["modes"][current_mode][final_grp] = []
                        current_did_entry["modes"][current_mode][final_grp].append(item)
                    else:
                        # Flat Mode (Legacy / Simple)
                        # Remove group for simple output as requested
                        if "group" in item:
                             del item["group"]

                        current_did_entry["items"].append(item)


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
