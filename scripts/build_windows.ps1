$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --noconfirm `
  --windowed `
  --name StainSpotCounter `
  --collect-all skimage `
  --collect-all scipy `
  --collect-all pandas `
  desktop_app.py

Write-Host "Build finished: dist\StainSpotCounter\StainSpotCounter.exe"
