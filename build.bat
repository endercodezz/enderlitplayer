@echo off
set PYTHON=python

%PYTHON% -m pip install --upgrade pip
%PYTHON% -m pip install pyinstaller

%PYTHON% generate_icon.py
%PYTHON% -m PyInstaller --noconfirm --onefile --windowed --name EnderlitPlayer --icon icon.ico desktop_app.py

echo Build complete. Check the dist folder.
