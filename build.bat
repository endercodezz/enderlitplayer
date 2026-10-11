@echo off
rem Builds dist\EnderlitPlayer-<version>-Windows-Portable.zip and dist\SHA256SUMS.txt
setlocal
if "%PYTHON%"=="" set PYTHON=python

%PYTHON% -m pip install --upgrade pip || exit /b 1
%PYTHON% -m pip install -r requirements.txt || exit /b 1
%PYTHON% -m pip install -e ".[build]" || exit /b 1
%PYTHON% scripts\build_windows.py || exit /b 1

echo Build complete. See the dist folder.
