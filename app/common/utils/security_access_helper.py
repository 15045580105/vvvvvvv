import os
import sys
import struct
import subprocess
import winreg
import tempfile
from typing import Optional, Tuple

class SecurityAccessHelper:
    _cached_python_32bit = None
    _cached_shim_script = None

    @staticmethod
    def calculate_key(level: int, seed: bytes, dll_path: str = None) -> Tuple[Optional[bytes], str]:
        """
        使用 32 位 Python 子进程调用 DLL 计算安全密钥。
        Returns:
            (key_bytes, error_message)
        """
        if not dll_path:
            try:
                from app.core.dependency_injection import di_container
                from app.services.configuration.config_service import AppConfigurationService

                config_service = di_container.resolve(AppConfigurationService)
                if not config_service:
                    config_service = AppConfigurationService()
                    # 注册单例，确保后续调用复用同一实例（避免重复读取文件）
                    di_container.register_singleton(AppConfigurationService, config_service)

                dll_path = config_service.diag_layer_settings.get("dll_path", "")
            except Exception:
                pass

        if not dll_path:
            return None, "错误: 未配置 DLL 路径"

        if not SecurityAccessHelper._cached_shim_script:
            SecurityAccessHelper._cached_shim_script = SecurityAccessHelper._create_shim_script()
        shim_script = SecurityAccessHelper._cached_shim_script

        if SecurityAccessHelper._cached_python_32bit is None:
            found = SecurityAccessHelper._find_32bit_python()
            SecurityAccessHelper._cached_python_32bit = found if found else ""
        python_32bit = SecurityAccessHelper._cached_python_32bit

        if not python_32bit:
            return None, "错误: 未找到 32 位 Python 环境，无法加载 32 位 DLL"

        if not os.path.exists(dll_path):
            return None, f"错误: DLL 文件不存在: {dll_path}"

        try:
            # 调用子进程
            cmd = [
                python_32bit,
                shim_script,
                dll_path,
                str(level),
                seed.hex(),
                "" # variant
            ]

            # 隐藏控制台窗口 (Windows)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            child_env = SecurityAccessHelper._build_32bit_child_env(python_32bit)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                env=child_env,
                text=True
            )
            stdout, stderr = process.communicate()

            for line in stdout.splitlines():
                if line.strip().startswith("KEY:"):
                    key_hex = line.strip().split("KEY:")[1]
                    try:
                        return bytes.fromhex(key_hex), ""
                    except ValueError:
                        return None, f"密钥格式错误: {key_hex}"

            err_msg = stderr.strip() or stdout.strip()
            return None, f"密钥计算失败 (Code {process.returncode}): {err_msg}"

        except Exception as e:
            return None, f"调用安全算法异常: {e}"

    @staticmethod
    def _find_32bit_python() -> Optional[str]:
        """尝试查找系统中安装的 32 位 Python 解释器路径。"""

        # 0. 检查当前进程是否为 32 位
        if struct.calcsize("P") * 8 == 32:
            return sys.executable

        # 0.1 允许通过环境变量显式指定 32 位 Python
        # - PYTHON_32BIT: 直接指向 python.exe
        env_exe = os.environ.get("PYTHON_32BIT")
        if env_exe and os.path.exists(env_exe):
            return env_exe

        # - PYTHON32_HOME: 指向 32 位 Python 根目录
        env_home = os.environ.get("PYTHON32_HOME")
        if env_home:
            cand = os.path.join(env_home, "python.exe")
            if os.path.exists(cand):
                return cand

        # 1. 优先查找打包环境或当前目录下附带的 32 位 Python 环境
        # 约定打包到 runtime32/python.exe
        search_roots = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            # onedir：exe 同级目录
            search_roots.append(exe_dir)
            # PyInstaller >= 6 onedir: 额外文件通常在 _internal 下
            search_roots.append(os.path.join(exe_dir, "_internal"))
            # onefile：解包临时目录
            if hasattr(sys, '_MEIPASS'):
                search_roots.append(sys._MEIPASS)
        else:
            search_roots.append(os.getcwd())
            try:
                search_roots.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
            except Exception:
                pass

        for root in search_roots:
            # 检查常见路径
            for rel in ["runtime32/python.exe", "python32/python.exe", "tools/python32/python.exe"]:
                p = os.path.join(root, rel)
                if os.path.exists(p):
                    return p
            # 扫描包含 python 和 32 的文件夹
            try:
                if os.path.exists(root):
                    for item in os.listdir(root):
                        full_path = os.path.join(root, item)
                        if os.path.isdir(full_path) and "python" in item.lower() and "32" in item.lower():
                            p = os.path.join(full_path, "python.exe")
                            if os.path.exists(p):
                                return p
            except Exception:
                pass

        # 2. 尝试通过 py launcher 查找 (py -0 --list)
        try:
            result = subprocess.run(["py", "-0", "--list"], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "32-bit" in line:
                        parts = line.strip().split()
                        if parts:
                            ver_tag = parts[0]  # e.g. -V:3.10-32
                            path_res = subprocess.run(
                                ["py", ver_tag, "-c", "import sys; print(sys.executable)"],
                                capture_output=True,
                                text=True,
                            )
                            if path_res.returncode == 0:
                                exe_path = path_res.stdout.strip()
                                if os.path.exists(exe_path):
                                    return exe_path
        except Exception:
            pass

        # 3. 尝试通过注册表查找
        try:
            for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Python\PythonCore") as key:
                        i = 0
                        while True:
                            try:
                                ver = winreg.EnumKey(key, i)
                                if ver.endswith("-32"):
                                    with winreg.OpenKey(key, f"{ver}\\InstallPath") as path_key:
                                        install_path, _ = winreg.QueryValueEx(path_key, "")
                                        exe_path = os.path.join(install_path, "python.exe")
                                        if os.path.exists(exe_path):
                                            return exe_path
                                i += 1
                            except OSError:
                                break
                except OSError:
                    pass
        except Exception:
            pass

        # 4. 尝试常见的安装路径
        common_paths = [
            r"C:\Python37-32\python.exe",
            r"C:\Python38-32\python.exe",
            r"C:\Python39-32\python.exe",
            r"C:\Python310-32\python.exe",
            r"C:\Python311-32\python.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python37-32\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python38-32\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python39-32\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python310-32\python.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path


        return None

    @staticmethod
    def _build_32bit_child_env(python_32bit: str) -> dict:
        """Build an isolated environment for the 32-bit helper process.

        The main application is a 64-bit process.  Do not prepend bundled
        32-bit DLL/Python paths to the main process PATH; only the child process
        that loads the 32-bit DLL receives those paths.
        """
        env = os.environ.copy()
        runtime_home = os.path.dirname(os.path.abspath(python_32bit))
        dll_dirs = [
            runtime_home,
            os.path.join(runtime_home, "DLLs"),
            os.path.join(runtime_home, "Library", "bin"),
        ]
        existing_path = env.get("PATH", "")
        env["PATH"] = os.pathsep.join([p for p in dll_dirs if os.path.isdir(p)] + [existing_path])
        env.setdefault("PYTHONHOME", runtime_home)
        env.setdefault("PYTHON32_HOME", runtime_home)
        env.setdefault("PYTHON_32BIT", os.path.abspath(python_32bit))
        return env

    @staticmethod
    def _create_shim_script() -> str:
        """
        在临时目录创建 shim 脚本文件，并返回其路径。
        用于解决打包后找不到原始 .py 文件的问题。
        """
        content = SecurityAccessHelper._get_shim_script_content()
        tmp_dir = tempfile.gettempdir()
        shim_path = os.path.join(tmp_dir, "vcc_security_access_shim.py")

        try:
            with open(shim_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        except Exception:
            # 如果写入失败（例如权限问题），尝试用随机文件名
            fd, shim_path = tempfile.mkstemp(suffix=".py", prefix="vcc_shim_", text=True)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

        return shim_path

    @staticmethod
    def _get_shim_script_content() -> str:
        return r"""
import sys
import ctypes
import os

def main():
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

    libs = []
    try:
        libs.append(("CDLL", ctypes.CDLL(dll_path)))
    except Exception as e:
        pass

    try:
        libs.append(("WinDLL", ctypes.WinDLL(dll_path)))
    except Exception as e:
        pass

    if not libs:
        print("Error: Could not load DLL with CDLL or WinDLL", file=sys.stderr)
        sys.exit(1)

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

    try:
        seed_bytes = bytes.fromhex(seed_hex)
    except ValueError:
        print("错误: 无效的种子十六进制字符串")
        sys.exit(1)

    seed_len = len(seed_bytes)
    seed_array = (ctypes.c_ubyte * seed_len)(*seed_bytes)

    max_key_len = 32
    key_array = (ctypes.c_ubyte * max_key_len)()
    actual_key_len = ctypes.c_uint(0)

    variant_bytes = variant.encode('ascii')

    func.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint)
    ]
    func.restype = ctypes.c_uint

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

        key_len = actual_key_len.value
        if key_len == 0:
             if ret != 0:
                 print(f"错误: DLL 函数返回 {ret} 且密钥长度为 0")
                 sys.exit(1)
             else:
                 pass

        if key_len > max_key_len:
             print(f"错误: 密钥长度 {key_len} 超过缓冲区")
             sys.exit(1)

        key_bytes = bytes(key_array[:key_len])
        print(f"KEY:{key_bytes.hex(' ').upper()}")
        sys.exit(0)

    except Exception as e:
        print(f"错误: 执行函数异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
"""
