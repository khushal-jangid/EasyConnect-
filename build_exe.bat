@echo off
title EasyConnect - Build Standalone EXE
cd /d "%~dp0"

echo ======================================================
echo    ⚡ EasyConnect - Building Standalone EXE (.exe)
echo ======================================================
echo.

python build_exe.py
pause
