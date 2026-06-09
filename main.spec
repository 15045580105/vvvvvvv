# -*- mode: python ; coding: utf-8 -*-

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


a = Analysis(
    ['main.py'],
    pathex=[_spec_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=[],
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
