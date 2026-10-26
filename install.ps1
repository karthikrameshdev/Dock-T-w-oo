param([switch]$NoAutostart,[switch]$NoStart)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
py -3.12 -m venv build/install-venv
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 first.' }
$python=Join-Path $PSScriptRoot 'build/install-venv/Scripts/python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed' }
& $python -m pip install '.[build]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$buildArgs=@('scripts/build_app.py','--install')
if ($NoAutostart) {$buildArgs+='--no-autostart'}
if ($NoStart) {$buildArgs+='--no-start'}
& $python @buildArgs
if ($LASTEXITCODE -ne 0) { throw 'Application build/install failed' }
