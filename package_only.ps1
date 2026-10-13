# 只打包，不进行编译
$iscc = "C:\Program Files (x86)\Inno Setup 6\iscc.exe"

if (Test-Path $iscc) {
    Write-Host "找到 Inno Setup 编译器: $iscc"
    Write-Host "开始打包..."
    & $iscc ".\packaging\VCC.iss"
    Write-Host "打包完成！安装包应在 installer_output 目录下。"
} else {
    Write-Host "未在默认路径找到 Inno Setup ($iscc)。"
    Write-Host "如果您已将其添加至环境变量，尝试直接运行 iscc.exe..."
    try {
        iscc ".\packaging\VCC.iss"
        Write-Host "打包完成！安装包应在 installer_output 目录下。"
    } catch {
        Write-Host "打包失败，请确保已安装 Inno Setup。" -ForegroundColor Red
    }
}

