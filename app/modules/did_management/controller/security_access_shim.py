import sys
import ctypes
import argparse
import os

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="32位安全访问垫片脚本")
    parser.add_argument("--dll", required=True, help="32位 DLL 路径")
    parser.add_argument("--level", type=int, required=True, help="安全等级")
    parser.add_argument("--seed", required=True, help="种子 (十六进制字符串)")
    parser.add_argument("--variant", default="", help="变体字符串 (可选)")

    args = parser.parse_args()

    dll_path = args.dll
    level = args.level
    seed_hex = args.seed.replace(" ", "")
    variant = args.variant

    if not os.path.exists(dll_path):
        print(f"错误: DLL 未找到: {dll_path}")
        sys.exit(1)

    try:
        # 加载 DLL
        lib = ctypes.CDLL(dll_path)
    except OSError as e:
        print(f"错误: 加载 DLL 失败: {e}")
        sys.exit(1)

    # 尝试查找函数。常见的 ASAP1A/VBT 函数名:
    # GenerateKeyEx, VbtSecurityAccess_GenerateKey, GenerateKeyExOpt
    func = None
    func_name = ""

    candidates = ["GenerateKeyEx", "VbtSecurityAccess_GenerateKey", "GenerateKeyExOpt"]
    for name in candidates:
        if hasattr(lib, name):
            func = getattr(lib, name)
            func_name = name
            break

    if not func:
        print(f"错误: 在 DLL 中未找到密钥生成函数。已尝试: {candidates}")
        sys.exit(1)

    # 准备参数
    # VbtSecurityAccess_GenerateKey(
    #   const unsigned char* ipSeedArray,
    #   unsigned int iSeedArraySize,
    #   const unsigned int iSecurityLevel,
    #   const char* ipVariant,
    #   unsigned char* iopKeyArray,
    #   unsigned int iMaxKeyArraySize,
    #   unsigned int* oActualKeyArraySize
    # )

    try:
        seed_bytes = bytes.fromhex(seed_hex)
    except ValueError:
        print("错误: 无效的种子十六进制字符串")
        sys.exit(1)

    seed_len = len(seed_bytes)
    seed_array = (ctypes.c_ubyte * seed_len)(*seed_bytes)

    # 最大密钥缓冲区大小 (通常与种子相同或稍大，32字节对大多数情况足够)
    max_key_len = 32
    key_array = (ctypes.c_ubyte * max_key_len)()
    actual_key_len = ctypes.c_uint(0)

    variant_bytes = variant.encode('ascii')

    # 定义参数类型以确保安全
    func.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte), # ipSeedArray
        ctypes.c_uint,                  # iSeedArraySize
        ctypes.c_uint,                  # iSecurityLevel
        ctypes.c_char_p,                # ipVariant
        ctypes.POINTER(ctypes.c_ubyte), # iopKeyArray
        ctypes.c_uint,                  # iMaxKeyArraySize
        ctypes.POINTER(ctypes.c_uint)   # oActualKeyArraySize
    ]
    func.restype = ctypes.c_uint # 通常返回状态 (0 = OK)

    try:
        ret = func(
            seed_array,
            seed_len,
            level,
            variant_bytes,
            key_array,
            max_key_len,
            ctypes.byref(actual_key_len)
        )

        if ret != 0:
            print(f"错误: DLL 函数返回非零状态: {ret}")
            sys.exit(1)

        # 提取密钥
        key_len = actual_key_len.value
        if key_len > max_key_len:
             print(f"错误: 密钥长度 {key_len} 超过缓冲区")
             sys.exit(1)

        key_bytes = bytes(key_array[:key_len])
        print(key_bytes.hex().upper())
        sys.exit(0)

    except Exception as e:
        print(f"错误: 执行函数异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

