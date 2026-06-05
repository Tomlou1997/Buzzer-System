@echo off
chcp 65001 >nul
echo 启动主控端（管理员）...
start "" python "%~dp0server.py"
