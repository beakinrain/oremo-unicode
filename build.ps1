# Build OREMO Unicode edition -> dist\OREMO
# requires: Python 3.10+ with tkinter;  pip install numpy sounddevice pyinstaller
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install numpy sounddevice pyinstaller
}
.\.venv\Scripts\pyinstaller.exe oremo.spec --noconfirm --log-level WARN
Copy-Item -Recurse -Force res\* dist\OREMO\
New-Item -ItemType Directory -Force dist\OREMO\source | Out-Null
Copy-Item -Recurse -Force src\* dist\OREMO\source\
Copy-Item -Force oremo.spec, build.ps1 dist\OREMO\source\
Get-ChildItem dist\OREMO\source -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Write-Host "done: dist\OREMO"
