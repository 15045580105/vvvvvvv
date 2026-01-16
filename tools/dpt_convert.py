import sys
import os
import json
import argparse

# Add workspace root to path
# This file is in tools/, so root is ../
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.common.utils.dpt_excel_loader import parse_excel_to_json_structure
from app.common.utils.crypto_utils import dpt_encryptor

def main():
    # --- Configuration ---
    # Please modify these paths as needed
    # 请在此处修改输入输出路径
    INPUT_FILE = r"D:\GAC客户提供\GAC DPT_Project_T75_CCU_V1.4_20251210.xlsx"  # Replace with your Excel path
    OUTPUT_FILE = r"D:\GAC客户提供\dpt_config.dat"                             # Replace with your Output path
    # ---------------------

    parser = argparse.ArgumentParser(description="Convert DPT Excel to Encrypted JSON")
    parser.add_argument("--input", "-i", help="Path to input .xlsx file", default=INPUT_FILE)
    parser.add_argument("--output", "-o", help="Path to output encrypted file", default=OUTPUT_FILE)

    args = parser.parse_args()

    input_path = args.input
    output_path = args.output

    if not input_path or not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}")
        print("Please edit the INPUT_FILE variable in the script or provide --input argument.")
        return

    print(f"Reading {input_path}...")
    try:
        data = parse_excel_to_json_structure(input_path)
    except Exception as e:
        print(f"Error parsing Excel: {e}")
        import traceback
        traceback.print_exc()
        return

    # Count DIDs and DTCs from new structure
    total_dids = 0
    total_dtcs = 0
    sheets_data = data.get("sheets", {})

    for sheet_name, content in sheets_data.items():
        total_dids += len(content.get("dids", []))
        total_dtcs += len(content.get("dtcs", []))

    print(f"Found {total_dids} DIDs and {total_dtcs} DTCs across {len(sheets_data)} sheets.")

    # --- Added Debug Output ---
    # Save unencrypted JSON for verification
    debug_output_path = os.path.splitext(output_path)[0] + "_debug.json"
    print(f"Writing unencrypted debug JSON to: {debug_output_path}")
    try:
        with open(debug_output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to write debug JSON: {e}")
    # --------------------------

    print("Encrypting data...")
    # Using ensure_ascii=False to keep Chinese readable in raw JSON (before encryption)
    # Using separators to minimize size
    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    encrypted_bytes = dpt_encryptor.encrypt(json_str)

    print(f"Writing {output_path}...")

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created directory: {output_dir}")
        except OSError as e:
            print(f"Error creating directory {output_dir}: {e}")
            return

    with open(output_path, "wb") as f:
        f.write(encrypted_bytes)

    print("Done.")

if __name__ == "__main__":
    main()

