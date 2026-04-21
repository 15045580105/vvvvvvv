# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE

_spec_dir = os.path.abspath(os.getcwd())

# 默认使用系统安装的 32 位 Python 作为打包来源不再依赖 build/python32_min。
# 如需临时覆盖，仍可通过环境变量 PYTHON32_HOME 指定。
_default_python32_home = r"C:\Program Files (x86)\Python39-32"

# 收集 32 位 Python 运行时到 onefile exe 内部（运行时解压到 sys._MEIPASS/runtime32）
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

if _python32_home and os.path.exists(_python32_home):
    datas += _collect_dir_datas(_python32_home, "runtime32")


a = Analysis(
    ['main.py'],
    pathex=[_spec_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main',
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
    icon=['D:\\UID01728\\Downloads\\vcc_logo\\vcc_logo.ico'],
    exclude_binaries=False,
)

# onefile 模式：不使用 COLLECT（COLLECT 会生成 onedir 文件夹）
