import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from app.common.utils.common_service_excel_loader import convert_common_service_excel, parse_common_service_excel


def main():
    """命令行入口：把常用服务 Excel 转成统一 JSON，或仅预览结构摘要。"""
    # 这是“Excel -> JSON”链路的最外层入口之一：
    # - `--preview` 用来快速确认识别到了多少条 `$2E` / `$31/$2F` 服务；
    # - 正常模式会调用转换器落盘为统一 JSON，后续界面直接消费这个文件。
    parser = argparse.ArgumentParser(description="将常用服务 Excel 文件转换为统一 JSON 配置。")
    parser.add_argument("input", help="输入 Excel 文件路径")
    parser.add_argument("-o", "--output-dir", default=".", help="输出目录，默认当前目录")
    parser.add_argument("-f", "--filename", default="common_service_config.json", help="输出文件名")
    parser.add_argument("--preview", action="store_true", help="仅预览结构摘要，不写文件")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if args.preview:
        data = parse_common_service_excel(str(input_path))
        summary = {
            "services2E": len(data.get("services2E", [])),
            "services31_2F": len(data.get("services31_2F", [])),
            "sourceFile": data.get("meta", {}).get("sourceFile"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    output_path = convert_common_service_excel(str(input_path), str(output_dir), args.filename)
    print(output_path)


if __name__ == "__main__":
    main()

