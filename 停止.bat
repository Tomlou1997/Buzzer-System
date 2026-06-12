@echo off
chcp 65001 >nul
echo 正在关闭抢答系统...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8888" ^| findstr "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)
echo ✅ 已关闭
pause
