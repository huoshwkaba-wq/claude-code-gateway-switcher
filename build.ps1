$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ClaudeGatewaySwitcher --icon "$PSScriptRoot\assets\app_icon.ico" --add-data "$PSScriptRoot\assets;assets" app.py
