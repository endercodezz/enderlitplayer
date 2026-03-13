param(
    [string]$Python = "python"
)

& $Python -m pip install --upgrade pip
& $Python -m pip install pyinstaller

& $Python generate_icon.py
& $Python -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name EnderlitPlayer `
    --icon icon.ico `
    desktop_app.py

Write-Host "Build complete. Check the dist folder."
