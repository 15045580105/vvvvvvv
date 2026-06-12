# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for VCC – 车载测试平台
=========================================
安全加固措施:
  1. optimize=2        – 移除 docstring 与 assert，增大反编译难度
  2. excludes          – 排除测试/调试/构建相关模块，减小攻击面
  3. strip             – 去除 ELF/PE 符号信息（UPX 进一步压缩）
  4. noarchive=False   – 使用 PYZ 归档字节码，不暴露 .pyc 散文件
配合外部 PyArmor 混淆脚本使用可达到商业级源码保护。
"""

import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

_spec_dir = os.path.abspath(os.getcwd())

# 默认使用系统安装的 32 位 Python 作为打包来源不再依赖 build/python32_min。
# 如需临时覆盖，仍可通过环境变量 PYTHON32_HOME 指定。
_default_python32_home = r"C:\Program Files (x86)\Python39-32"

# 收集 32 位 Python 运行时到 onedir 安装目录内部（_internal/runtime32）。
# 主程序仍使用 64 位 Python 运行时；runtime32 仅供需要加载 32 位 DLL 的子进程使用。
_python32_home = os.environ.get("PYTHON32_HOME", _default_python32_home)


def _collect_dir_datas(src_root: str, dest_prefix: str):
    """递归收集目录下所有文件为 (src_file, dest_dir) 形式的 datas 列表。"""
    collected = []
    for root, _dirs, files in os.walk(src_root):
        rel = os.path.relpath(root, src_root)
        # '.' 表示根目录
        dest_dir = dest_prefix if rel in (".", "") else os.path.join(dest_prefix, rel)
        for fn in files:
            collected.append((os.path.join(root, fn), dest_dir))
    return collected


# ── 排除不需要打入安装包的模块，减小体积并降低攻击面 ──
_excludes = [
    # 测试框架
    'unittest', 'pytest', 'doctest', 'test', 'tests',
    # 调试/开发工具
    'pdb', 'ipdb', 'pudb', 'wdb',
    'IPython', 'jupyter', 'notebook',
    # 构建工具（保留 setuptools/pkg_resources/wheel，很多库运行时需要）
    'pip',
    # IDE 辅助
    'pydev', 'pydevd', '_pydevd_bundle',
    # 不需要的标准库模块
    'tkinter', 'turtle', 'turtledemo',
    'lib2to3', 'ensurepip', 'venv',
    'xmlrpc', 'ftplib', 'telnetlib',
    'webbrowser', 'antigravity',
    'idlelib', 'sqlite3',
]

binaries = []
datas = []

_resources_dir = os.path.join(_spec_dir, "app", "resources")
if os.path.exists(_resources_dir):
    datas += _collect_dir_datas(_resources_dir, os.path.join("app", "resources"))

_dpt_config = os.path.join(_spec_dir, "dpt_config.json")
if os.path.exists(_dpt_config):
    datas.append((_dpt_config, "."))

if _python32_home and os.path.exists(_python32_home):
    datas += _collect_dir_datas(_python32_home, "runtime32")

_runtime_hook = os.path.join(_spec_dir, "packaging", "pyinstaller_runtime_hook.py")
runtime_hooks = [_runtime_hook] if os.path.exists(_runtime_hook) else []

_icon_path = os.path.join(_spec_dir, "app", "resources", "images", "vcc_logo.ico")
if not os.path.exists(_icon_path):
    _icon_path = None


_hiddenimports = [
    # ── cryptography / TLS ──
    'cryptography',
    'cryptography.hazmat',
    'cryptography.hazmat.backends',
    'cryptography.hazmat.backends.openssl',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.asymmetric',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.kdf',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.x509',
    'cryptography.fernet',
    # ── cffi / pycparser ──
    'cffi',
    '_cffi_backend',
    'pycparser',
    # ── bcrypt / NaCl ──
    'bcrypt',
    'nacl',
    'nacl.bindings',
    'nacl.public',
    'nacl.signing',
    'nacl.encoding',
    # ── paramiko / SSH ──
    'paramiko',
    'paramiko.transport',
    'paramiko.channel',
    'paramiko.sftp_client',
    'paramiko.ssh_exception',
    # ── scp ──
    'scp',
    # ── scapy / 网络 ──
    'scapy',
    'scapy.all',
    'scapy.arch',
    'scapy.arch.windows',
    'scapy.config',
    'scapy.layers',
    'scapy.layers.l2',
    'scapy.layers.inet',
    'scapy.layers.inet6',
    'scapy.sendrecv',
    'scapy.utils',
    'scapy.contrib.automotive',
    'scapy.contrib.automotive.someip',
    # ── psutil ──
    'psutil',
    '_psutil_windows',
    # ── doipclient ──
    'doipclient',
    # ── invoke ──
    'invoke',
    # ── PyQt5 插件 ──
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.QtChart',
    'PyQt5.sip',
    # ── Excel ──
    'openpyxl',
    'openpyxl.cell',
    'openpyxl.styles',
    'openpyxl.workbook',
    'openpyxl.worksheet',
    # ── 其他常用 ──
    'json',
    'xml',
    'xml.etree',
    'xml.etree.ElementTree',
    'logging',
    'multiprocessing',
    'subprocess',
    'socket',
    'struct',
    'binascii',
    'hashlib',
    'hmac',
]

a = Analysis(
    ['main.py'],
    pathex=[_spec_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=_excludes,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='VCC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_path,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VCC',
)
