@echo off
title EasyConnect - PC Agent
chcp 65001 > nul
set PYTHONUNBUFFERED=1
cd /d "%~dp0"

python -u agent.py
pause
