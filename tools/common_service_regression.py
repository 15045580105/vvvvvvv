import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
	sys.path.insert(0, str(WORKSPACE_ROOT))

from app.common.utils.common_service_excel_loader import parse_common_service_excel


def main():
	parser = argparse.ArgumentParser(description="回归生成常用服务转换结果，便于检查新 JSON 结构。")
	parser.add_argument("input", nargs="?", default=str(WORKSPACE_ROOT / "VCC工具.xlsx"), help="输入 Excel 路径")
	parser.add_argument("output", nargs="?", default=str(WORKSPACE_ROOT / "common_service_regression_output.json"), help="输出 JSON 路径")
	args = parser.parse_args()

	input_path = Path(args.input).expanduser().resolve()
	output_path = Path(args.output).expanduser().resolve()
	data = parse_common_service_excel(str(input_path))
	output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
	print(output_path)


if __name__ == "__main__":
	main()


