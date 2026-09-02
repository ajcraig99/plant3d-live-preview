# p3dpreview.ps1 - launch the Plant 3D live preview server from PowerShell.
#   .\p3dpreview.ps1 --root C:\path\to\your\plant3d\scripts
#   .\p3dpreview.ps1 --port 9000 --no-open
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Here ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "[p3dpreview] creating venv..."
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { & py -3 -m venv $Venv } else { & python -m venv $Venv }
}

& $Py -c "import manifold3d, trimesh, scipy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[p3dpreview] installing dependencies (first run)..."
    & $Py -m pip install --quiet --upgrade pip
    & $Py -m pip install --quiet -r (Join-Path $Here "requirements.txt")
}

& $Py (Join-Path $Here "server.py") @args
