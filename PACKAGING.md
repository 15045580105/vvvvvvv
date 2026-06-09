# VCC 安装包构建说明

本项目现在使用“两阶段发布”：

1. PyInstaller 生成目录版程序：`dist\VCC\VCC.exe`
2. Inno Setup 把目录版程序打成完整安装包：`installer_output\VCC_Setup_1.0.0.exe`

## 功能

- 不再生成单文件 EXE，避免运行时临时解压导致的路径、DLL、权限问题。
- 安装程序支持选择安装路径。
- 安装程序支持勾选创建桌面快捷方式。
- 64 位主程序运行环境由 PyInstaller 打入 `_internal`。
- 32 位 Python 运行环境打入 `_internal\runtime32`，只给 32 位 DLL 子进程使用，不修改 64 位主程序 PATH。
- 本地 `app` 业务代码不以 `.py` 源码形式复制到发布目录，而是进入 PyInstaller 的 PYZ 字节码归档。

## 前置要求

- 当前项目 64 位虚拟环境可运行 PyInstaller。
- 本机存在 32 位 Python，例如：`C:\Program Files (x86)\Python39-32`。
- 如需生成安装包，需要安装 Inno Setup 6。

## 一键构建

在 PowerShell 中执行：

```powershell
Set-Location -Path 'D:\VCC'
.\build_installer.ps1
```

如果 32 位 Python 不在默认位置：

```powershell
Set-Location -Path 'D:\VCC'
.\build_installer.ps1 -Python32Home 'C:\Path\To\PythonXX-32'
```

如果只想生成目录版程序，不编译安装包：

```powershell
Set-Location -Path 'D:\VCC'
.\build_installer.ps1 -SkipInstaller
```

如果 Inno Setup 不在默认位置：

```powershell
Set-Location -Path 'D:\VCC'
.\build_installer.ps1 -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

## 输出

- 目录版程序：`dist\VCC\VCC.exe`
- 安装包：`installer_output\VCC_Setup_1.0.0.exe`

## 32 位 DLL 调用说明

`app\common\utils\security_access_helper.py` 会查找安装目录内的 `_internal\runtime32\python.exe`，并只在该子进程环境中加入：

- `_internal\runtime32`
- `_internal\runtime32\DLLs`
- `_internal\runtime32\Library\bin`

因此 32 位 DLL 能由 32 位 Python 子进程加载，同时不会影响 64 位主程序自身的运行环境。

## 代码保护说明

PyInstaller 发布目录不会复制本地 `app` 业务源码 `.py` 文件；构建脚本会自动检查这一点。当前保护级别是“字节码归档保护”，可防止直接查看源码文件，但不是不可逆的商业级混淆。如果后续需要更强保护，可在该流程前增加 PyArmor/Nuitka 等混淆或编译步骤。

