#!/usr/bin/env python3
"""提取 ICC Server 的所有 Event/Method 定义，生成 ICC_SERVICES 字典代码。"""

import openpyxl

EXCEL_PATH = r'd:\奇瑞\ICC SOMEIP Services Interface Description V4.400（For EEA5.1）20251030.xlsx'

wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)

# Sheet 1: 服务定义 (Event/Method)
ws_def = wb.worksheets[3]
# Sheet 3: SOMEIP通信行为定义 (Server/Client/Port)
ws_svc = wb.worksheets[5]

# 1) 解析通信行为定义，获取 ICC 作为 Server 的服务列表
icc_server_services = {}  # svc_id_hex -> {name, proto, server_ip, server_port, ...}
for row in ws_svc.iter_rows(min_row=2, max_row=ws_svc.max_row, values_only=True):
    if row[0] is None and row[1] is None:
        continue
    svc_name = str(row[0] or "").strip()
    svc_id = str(row[1] or "").strip()
    server_ecu = str(row[10] or "").strip()
    if "ICC" not in server_ecu:
        continue
    if svc_id not in icc_server_services:
        icc_server_services[svc_id] = {
            "name": svc_name,
            "service_id": svc_id,
            "instance_id": row[2],
            "major_version": row[3],
            "minor_version": row[4],
            "ttl": row[5],
            "vlan_id": row[6],
            "transport_protocol": str(row[9] or "").strip(),
            "server_ecu": server_ecu,
            "server_ip": str(row[11] or "").strip(),
            "server_port": row[13],
            "events": [],
            "rpcs": [],
        }

# 2) 解析服务定义 sheet，提取 Event/Method
current_svc_id = None
for row in ws_def.iter_rows(min_row=2, max_row=ws_def.max_row, values_only=True):
    # 新 service 行
    if row[0] is not None and row[1] is not None:
        svc_name = str(row[0] or "").strip()
        svc_id = str(row[1] or "").strip()
        current_svc_id = svc_id
        continue

    if current_svc_id is None or current_svc_id not in icc_server_services:
        continue

    rpc_type = str(row[3] or "").strip()
    method_event_name = str(row[7] or "").strip()
    method_event_id = str(row[8] or "").strip()
    eventgroup_info = str(row[10] or "").strip()
    proto = str(row[11] or "").strip()

    if not method_event_id or not rpc_type:
        continue

    # 解析 eventgroup ID
    eg_id = "0001"
    if "@" in eventgroup_info and "0x" in eventgroup_info:
        eg_id = eventgroup_info.split("0x")[-1].strip()

    svc = icc_server_services[current_svc_id]
    entry = (int(method_event_id, 16), int(eg_id, 16), proto)

    if rpc_type == "Event":
        svc["events"].append(entry)
    elif "Method" in rpc_type:
        svc["rpcs"].append((int(method_event_id, 16), proto))

# 3) 输出 Python 代码
print("# ICC 服务定义 (从 Excel 自动生成)")
print("# 格式: svc_id -> {name, events: [(event_id, eventgroup_id, proto)], rpcs: [(method_id, proto)]}")
print("ICC_SERVICES = {")
for svc_id in sorted(icc_server_services.keys()):
    svc = icc_server_services[svc_id]
    svc_int = int(svc_id, 16)
    print(f"    0x{svc_int:04X}: {{  # {svc['name']}")
    print(f"        \"name\": \"{svc['name']}\",")
    print(f"        \"instance_id\": 0x{int(svc['instance_id']):04X},")
    print(f"        \"major_version\": {svc['major_version']},")
    print(f"        \"server_ip\": \"{svc['server_ip']}\",")
    print(f"        \"server_port\": {svc['server_port']},")
    print(f"        \"transport\": \"{svc['transport_protocol']}\",")
    if svc["events"]:
        print(f"        \"events\": [")
        for evt_id, eg_id, proto in svc["events"]:
            print(f"            (0x{evt_id:04X}, 0x{eg_id:04X}, \"{proto}\"),")
        print(f"        ],")
    else:
        print(f"        \"events\": [],")
    if svc["rpcs"]:
        print(f"        \"rpcs\": [")
        for m_id, proto in svc["rpcs"]:
            print(f"            (0x{m_id:04X}, \"{proto}\"),")
        print(f"        ],")
    else:
        print(f"        \"rpcs\": [],")
    print(f"    }},")
print("}")

# 输出统计
print(f"\n# 共 {len(icc_server_services)} 个 ICC Server 服务")
for svc_id, svc in sorted(icc_server_services.items()):
    print(f"#   0x{int(svc_id,16):04X} ({svc['name']}): {len(svc['events'])} events, {len(svc['rpcs'])} methods, {svc['transport_protocol']}")
