import sys
import ctypes
import os

def main():
    # 手动解析参数，避免 argparse 的 usage 输出干扰
    # 预期参数: script.py <dll_path> <level> <seed_hex> [variant]
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <dll_path> <level> <seed_hex> [variant]", file=sys.stderr)
        sys.exit(1)

    dll_path = sys.argv[1]
    try:
        level = int(sys.argv[2])
    except ValueError:
        print("Error: Level must be an integer", file=sys.stderr)
        sys.exit(1)

    seed_hex = sys.argv[3].replace(" ", "")
    variant = sys.argv[4] if len(sys.argv) > 4 else ""

    if not os.path.exists(dll_path):
        print(f"错误: DLL 未找到: {dll_path}")
        sys.exit(1)

    # 尝试加载 DLL
    # 优先尝试 CDLL (cdecl)，如果失败或找不到函数，再尝试 WinDLL (stdcall)
    libs = []
    try:
        libs.append(("CDLL", ctypes.CDLL(dll_path)))
    except Exception as e:
        # print(f"Warning: CDLL load failed: {e}", file=sys.stderr)
        pass

    try:
        libs.append(("WinDLL", ctypes.WinDLL(dll_path)))
    except Exception as e:
        # print(f"Warning: WinDLL load failed: {e}", file=sys.stderr)
        pass

    if not libs:
        print("Error: Could not load DLL with CDLL or WinDLL", file=sys.stderr)
        sys.exit(1)

    # 尝试查找函数。常见的 ASAP1A/VBT 函数名:
    # GenerateKeyEx, VbtSecurityAccess_GenerateKey, GenerateKeyExOpt, GenerateKey
    func = None
    func_name = ""
    loaded_lib_type = ""

    candidates = ["GenerateKeyEx", "VbtSecurityAccess_GenerateKey", "GenerateKeyExOpt", "GenerateKey"]

    for lib_type, lib in libs:
        for name in candidates:
            if hasattr(lib, name):
                func = getattr(lib, name)
                func_name = name
                loaded_lib_type = lib_type
                break
        if func:
            break

    if not func:
        print(f"错误: 在 DLL 中未找到密钥生成函数。已尝试: {candidates}")
        sys.exit(1)

    # print(f"Debug: Using {func_name} from {loaded_lib_type}", file=sys.stderr)

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
            # 某些 DLL 返回 1 表示成功，或者其他非 0 值
            # 但标准通常是 0 = OK.
            # 如果 ret != 0，我们仍然检查 actual_key_len 是否有值
            pass
            # print(f"Warning: DLL function returned non-zero status: {ret}", file=sys.stderr)

        # 提取密钥
        key_len = actual_key_len.value
        if key_len == 0:
             # 如果长度为 0，可能是失败
             if ret != 0:
                 print(f"错误: DLL 函数返回 {ret} 且密钥长度为 0")
                 sys.exit(1)
             else:
                 # 也许是空密钥？
                 pass

        if key_len > max_key_len:
             print(f"错误: 密钥长度 {key_len} 超过缓冲区")
             sys.exit(1)

        key_bytes = bytes(key_array[:key_len])
        # 使用特定前缀以便调用者提取
        print(f"KEY:{key_bytes.hex(' ').upper()}")
        sys.exit(0)

    except Exception as e:
        print(f"错误: 执行函数异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

