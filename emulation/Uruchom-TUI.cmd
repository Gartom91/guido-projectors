@echo off
chcp 65001 >nul
pushd "%~dp0.."
wsl -d Ubuntu -- env TERM=xterm-256color LANG=C.UTF-8 python3 emulation/guido_emulator.py
if errorlevel 1 pause
popd
