#!/usr/bin/env python3
"""Scan the ICC SOMEIP Excel matrix and dump key information."""
import json
import openpyxl

MATRIX_PATH = r"d:\奇瑞\ICC SOMEIP Services Interface Description V4.400（For EEA5.1）20251030.xlsx"

def main():
    wb = openpyxl.load_workbook(MATRIX_PATH, read_only=True, data_only=True)
    try:
        print("=" * 80)
        print("Sheet names:")
        for i, name in enumerate(wb.sheetnames):
            print(f"  [{i}] {name!r}")
        print("=" * 80)

        # Scan each sheet's first few rows to find Deployment and service info
        for sheet_name in wb.sheetnames:
            if sheet_name in ('Logo', 'Application range', 'History'):
                continue
            sheet = wb[sheet_name]
            print(f"\n{'=' * 80}")
            print(f"Sheet: {sheet_name!r}")
            print(f"{'=' * 80}")
            rows = []
            for idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = [str(v).strip() if v is not None else "" for v in row]
                if any(values):
                    rows.append((idx, values[:20]))
                if len(rows) >= 8:
                    break
            for row_num, vals in rows:
                print(f"  Row {row_num}: {vals}")

        # Now specifically look for Deployment-like sheet (sheet index 3 or 4)
        # Let's do a deeper scan of the sheet that looks like it has deployment info
        print("\n\n" + "=" * 80)
        print("DEEP SCAN: Looking for Deployment / Service ID columns...")
        print("=" * 80)

        for sheet_name in wb.sheetnames:
            if sheet_name in ('Logo', 'Application range', 'History'):
                continue
            sheet = wb[sheet_name]
            all_rows = []
            for idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = [str(v).strip() if v is not None else "" for v in row]
                if any(values):
                    all_rows.append((idx, values[:25]))
                if len(all_rows) >= 50:
                    break

            # Check if any row contains "Service ID" or "service id"
            for row_num, vals in all_rows:
                joined = " | ".join(vals).lower()
                if "service id" in joined or "service_id" in joined or "serviceid" in joined:
                    print(f"\n  Found 'Service ID' in sheet {sheet_name!r}, Row {row_num}:")
                    print(f"    Headers: {vals}")
                    # Print next 20 data rows
                    data_count = 0
                    for r2, v2 in all_rows:
                        if r2 > row_num and data_count < 30:
                            print(f"    Row {r2}: {v2}")
                            data_count += 1
                    break

    finally:
        wb.close()


if __name__ == "__main__":
    main()
