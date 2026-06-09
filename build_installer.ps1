param(
    [string]$Python32Home = $env:PYTHON32_HOME,
    [string]$InnoCompiler = "",
    [switch]$SkipInstaller,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Resolve-Python32Home([string]$Candidate) {
    $candidates = @()
    if ($Candidate) { $candidates += $Candidate }
    $candidates += @(
        "C:\Program Files (x86)\Python39-32",
        "C:\Program Files (x86)\Python310-32",
        "C:\Program Files (x86)\Python311-32",
        "C:\Python39-32",
        "C:\Python310-32",
        "C:\Python311-32"
    )

    foreach ($item in $candidates) {
        if ($item -and (Test-Path (Join-Path $item "python.exe"))) {
            return (Resolve-Path $item).Path
        }
    }

    throw "32-bit Python was not found. Install 32-bit Python or pass -Python32Home 'C:\path\to\PythonXX-32'."
}

function Resolve-InnoCompiler([string]$Candidate) {
    if ($Candidate -and (Test-Path $Candidate)) {
        return (Resolve-Path $Candidate).Path
    }

    $default = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $default) {
        return $default
    }

    $userDefault = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    if (Test-Path $userDefault) {
        return $userDefault
    }

    $cmd = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "Inno Setup compiler ISCC.exe was not found. Install Inno Setup 6 or pass -InnoCompiler."
}

Write-Step "Check bundled 32-bit runtime source"
$ResolvedPython32Home = Resolve-Python32Home $Python32Home
$env:PYTHON32_HOME = $ResolvedPython32Home
Write-Host "32-bit Python: $ResolvedPython32Home"
& (Join-Path $ResolvedPython32Home "python.exe") -c "import struct, sys; assert struct.calcsize('P') * 8 == 32, sys.executable; print(sys.executable)"

if (-not $NoClean) {
    Write-Step "Clean previous build outputs"
    Remove-Item -Recurse -Force "$Root\build", "$Root\dist", "$Root\installer_output" -ErrorAction SilentlyContinue
}

Write-Step "Build onedir application with PyInstaller"
python -m PyInstaller --noconfirm --clean "$Root\main.spec"

$AppExe = "$Root\dist\VCC\VCC.exe"
$Runtime32Exe = "$Root\dist\VCC\_internal\runtime32\python.exe"
if (-not (Test-Path $AppExe)) {
    throw "Main executable was not generated: $AppExe"
}
if (-not (Test-Path $Runtime32Exe)) {
    throw "Bundled 32-bit runtime was not generated: $Runtime32Exe"
}

Write-Step "Validate runtime32 and local source protection"
& $Runtime32Exe -c "import struct, sys; assert struct.calcsize('P') * 8 == 32, sys.executable; print('bundled 32-bit python ok:', sys.executable)"

$LocalSourceLeaks = Get-ChildItem "$Root\dist\VCC" -Recurse -File -Filter "*.py" |
    Where-Object { $_.FullName -match "\\_internal\\app\\" }
if ($LocalSourceLeaks) {
    $LocalSourceLeaks | ForEach-Object { Write-Host $_.FullName -ForegroundColor Yellow }
    throw "Local app source .py files were copied to dist. Check PyInstaller datas configuration."
}
Write-Host "Local app code is not present as .py source files in dist; it is stored in the PyInstaller PYZ bytecode archive."

if ($SkipInstaller) {
    Write-Step "Skip installer compilation"
    Write-Host "Onedir application: $Root\dist\VCC"
    exit 0
}

Write-Step "Compile installer with Inno Setup"
$ISCC = Resolve-InnoCompiler $InnoCompiler
Write-Host "Inno Setup: $ISCC"
& $ISCC "$Root\packaging\VCC.iss"

$Setup = Get-ChildItem "$Root\installer_output" -Filter "VCC_Setup_*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Setup) {
    throw "Installer compilation finished but no setup executable was found."
}

Write-Step "Done"
Write-Host "Installer: $($Setup.FullName)" -ForegroundColor Green
Write-Host "Onedir application: $Root\dist\VCC" -ForegroundColor Green
