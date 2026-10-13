#!/usr/bin/env python3
"""Dump deployment sheet with ALL columns including ports."""
import sys
sys.path.insert(0, r"d:\VCC")
import openpyxl

EXCEL = r"d:\奇瑞\ICC SOMEIP Services Interface Description V4.400（For EEA5.1）20251030.xlsx"
wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
OUT = r"d:\VCC\tools\excel_deploy_full.txt"

out = []
def log(m):
    out.append(str(m))

# Find deployment sheet
dep_sheet = None
for name in wb.sheetnames:
    sheet = wb[name]
    for row in sheet.iter_rows(values_only=True, max_row=5):
        vals = [str(v).strip().lower() if v else "" for v in row]
        joined = " ".join(vals)
        if "service id" in joined and "server ip" in joined:
            dep_sheet = name
            break
    if dep_sheet:
        break

sheet = wb[dep_sheet]
rows = list(sheet.iter_rows(values_only=True))

# Find header row
header_idx = 0
for idx, row in enumerate(rows):
    vals = [str(v).strip().lower() if v else "" for v in row]
    if "service id" in " ".join(vals) and "server ip" in " ".join(vals):
        header_idx = idx
        headers = [str(v).strip() if v else "" for v in row]
        break

log(f"Sheet: {dep_sheet!r}")
log(f"Total headers: {len(headers)}")
for i, h in enumerate(headers):
    log(f"  Col {i}: {h!r}")

log("\n--- ICC services (192.168.62.31) ---")
for i, row in enumerate(rows[header_idx+1:]):
    vals = [str(v).strip() if v else "" for v in row]
    if len(vals) > 11 and "192.168.62.31" in vals[11]:
        # Show all columns
        log(f"\n  [{i+1}] {vals[0]} (0x{vals[1]})")
        for j in range(min(len(vals), 20)):
            if vals[j]:
                log(f"    Col {j} ({headers[j]}): {vals[j]}")

# Also check for "3 SOMEIP通信行为定义" sheet - it may have port info
log("\n\n--- Checking for port columns ---")
# The deployment sheet IS "3 SOMEIP通信行为定义", show cols 13-25
log(f"\nHeaders cols 13-30:")
for j in range(13, min(len(headers), 30)):
    log(f"  Col {j}: {headers[j]!r}")

# Show first ICC row with all columns
log("\n--- First ICC row, all columns ---")
for i, row in enumerate(rows[header_idx+1:]):
    vals = [str(v).strip() if v else "" for v in row]
    if len(vals) > 11 and "192.168.62.31" in vals[11]:
        log(f"Row {i+1}: {vals[0]}")
        for j in range(len(vals)):
            if vals[j]:
                log(f"  [{j:2d}] {headers[j] if j < len(headers) else '?'}: {vals[j]}")
        break

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(f"Written to {OUT}")
