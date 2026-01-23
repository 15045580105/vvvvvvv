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

# _process_did_rows removed. Data is parsed via dpt_excel_loader.
# _process_dtc_rows removed.

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

        # [NEW] Extract Session/Security Support
        session_support = {}
        for k in ["session_default", "session_extended", "session_programming"]:
            if k in did_entry:
                clean_key = k.replace("session_", "")
                session_support[clean_key] = did_entry[k]

        security_support = {}
        for k in ["security_locked", "security_level1", "security_level2", "security_level3", "security_level_flash"]:
            if k in did_entry:
                clean_key = k.replace("security_", "")
                security_support[clean_key] = did_entry[k]

        # Synthesize Strings for UI compatibility
        syn_session = "Default"

        def _is_supported_basic(val):
            s = str(val).strip().upper()
            return s in ["O", "YES", "TRUE", "SUPPORT", "SUPPORTED", "1", "X"] or s.startswith("X/") or "/X" in s

        if session_support:
            # Priority: Default -> Extended -> Programming (for Reading usually Default is best if supported)
            is_def = _is_supported_basic(session_support.get("default", ""))
            is_ext = _is_supported_basic(session_support.get("extended", ""))
            is_prg = _is_supported_basic(session_support.get("programming", ""))

            if is_def: syn_session = "Default (0x01)"
            elif is_ext: syn_session = "Extended (0x03)"
            elif is_prg: syn_session = "Programming (0x02)"

        syn_security = "Locked"
        if security_support:
            # Priority: Locked (None) -> Level 1 -> Level 3 -> Level Flash
            is_locked = _is_supported_basic(security_support.get("locked", ""))
            is_l1 = _is_supported_basic(security_support.get("level1", ""))
            is_l3 = _is_supported_basic(security_support.get("level3", ""))

            if is_locked: syn_security = "Locked"
            elif is_l1: syn_security = "Level 1 (0x01)"
            elif is_l3: syn_security = "Level 3 (0x03)"
            else:
                # Pick first available level
                for k, v in security_support.items():
                    if _is_supported_basic(v):
                         syn_security = k.title()
                         break

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

        # Flatten structure for parser processing
        # Structure: modes -> groups -> items list
        all_items = []
        if "modes" in did_entry:
            for mode, groups in did_entry["modes"].items():
                for group_name, items in groups.items():
                    for item in items:
                        # Copy item to modify group
                        new_item = item.copy()
                        # If mode is significant (not Default), prepend it to group
                        if mode != "Default":
                             new_item["group"] = f"{mode} - {group_name}" if group_name else mode
                        else:
                             new_item["group"] = group_name
                        all_items.append(new_item)
        elif "items" in did_entry:
            # Fallback for legacy flat structure
             all_items = did_entry["items"]

        # Sort items by byte, then bit
        items = sorted(all_items, key=lambda x: (
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

             # Extract Group
             group_val = item.get("group", "")

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
                                elif "unit" in k: lin_dict["unit"] = v
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
                         "bit_fields": {},
                         "group": group_val
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
                     "conversion": conv,
                     "group": group_val
                 })

        result["parsers"][did_key] = {
            "config": {"fields": fields},
            "meta": {
                "description": desc,
                "category": sheet,
                "diagnostic_session": syn_session,
                "security_access": syn_security,
                "raw_session_support": session_support,
                "raw_security_support": security_support
            }
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
            from app.common.utils.dpt_excel_loader import parse_excel_to_json_structure
        except ImportError:
             print("dpt_excel_loader not found")
             return

        try:
             # Use the unified Excel Loader
             data = parse_excel_to_json_structure(str(path))

             result = {"parsers": {}, "dtcs": {}}
             # Process structured data into runtime format
             _process_json_content(data, result)

             # Apply Parsers
             for did_key, info in result["parsers"].items():
                 config = info.get("config", {})
                 meta = info.get("meta", {})
                 fields = config.get("fields", [])
                 self._register_did_parser(did_key, fields, meta)

             # Apply DTCs
             if "dtcs" in result:
                 self._dtc_map.update(result["dtcs"])

        except Exception as e:
            print(f"Error loading Excel {path}: {e}")

    # Legacy parsers removed.


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

    def get_did_info(self, did: str) -> Optional[Dict[str, Any]]:
        """Get DID metadata (description, session support, etc.)."""
        did_key = did.strip().upper().replace("0X", "")
        return self._did_metadata.get(did_key)
