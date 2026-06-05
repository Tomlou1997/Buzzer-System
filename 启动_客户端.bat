@echo off
chcp 65001 >nul
echo 启动客户端（选手）...
start "" python "%~dp0client.py"
