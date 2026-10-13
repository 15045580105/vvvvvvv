#!/usr/bin/env python3
"""Debug: dump first 20 data rows from Excel service sheet."""
import sys
sys.path.insert(0, r"d:\VCC")
import openpyxl

EXCEL = r"d:\奇瑞\ICC SOMEIP Services Interface Description V4.400（For EEA5.1）20251030.xlsx"
wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)

target = None
for name in wb.sheetnames:
    sheet = wb[name]
    for row in sheet.iter_rows(values_only=True, max_row=5):
        vals = [str(v).strip().lower() if v else "" for v in row]
        if "service id" in " ".join(vals) and "method" in " ".join(vals):
            target = name
            break
    if target:
        break

print(f"Sheet: {target!r}")
sheet = wb[target]
rows = list(sheet.iter_rows(values_only=True))

# Find header row
for idx, row in enumerate(rows):
    vals = [str(v).strip().lower() if v else "" for v in row]
    if "service id" in " ".join(vals) and "method" in " ".join(vals):
        print(f"\nHeader at row {idx}")
        # Print next 20 rows (first 15 cols only)
        for i, r in enumerate(rows[idx+1:idx+21]):
            vals = [str(v).strip() if v else "" for v in r[:12]]
            print(f"  Row {idx+1+i}: {vals}")
        break
