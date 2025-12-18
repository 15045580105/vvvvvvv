import os
import subprocess
import winreg
from typing import Optional, Tuple

class SecurityAccessHelper:
    @staticmethod
    def calculate_key(level: int, seed: bytes, dll_path: str = r"D:\GAC客户提供\GAC_CCU_SA.dll") -> Tuple[Optional[bytes], str]:
        """
        使用 32 位 Python 子进程调用 DLL 计算安全密钥。
        Returns:
            (key_bytes, error_message)
        """
        shim_script = os.path.join(os.path.dirname(__file__), "security_access_shim.py")

        # 尝试寻找 32 位 Python
        python_32bit = SecurityAccessHelper._find_32bit_python()
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

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
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

        # 1. 尝试通过 py launcher 查找 (py -0 --list)
        try:
            result = subprocess.run(["py", "-0", "--list"], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "32-bit" in line:
                        parts = line.strip().split()
                        if parts:
                            ver_tag = parts[0] # e.g. -V:3.10-32
                            path_res = subprocess.run(
                                ["py", ver_tag, "-c", "import sys; print(sys.executable)"],
                                capture_output=True, text=True
                            )
                            if path_res.returncode == 0:
                                exe_path = path_res.stdout.strip()
                                if os.path.exists(exe_path):
                                    return exe_path
        except Exception:
            pass

        # 2. 尝试通过注册表查找
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

        # 3. 尝试常见的安装路径
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

        # 4. 如果用户在环境变量中配置了 PYTHON_32BIT
        env_path = os.environ.get("PYTHON_32BIT")
        if env_path and os.path.exists(env_path):
            return env_path

        return None

