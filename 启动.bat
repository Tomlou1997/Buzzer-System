@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================
echo     抢答系统 · 启动中...
echo ================================
echo [%date% %time%] === 抢答系统启动 === > start_log.txt

REM 关闭已在运行的实例
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8888" ^| findstr "LISTENING"') do (
    echo [%date% %time%] 关闭旧进程 PID=%%a >> start_log.txt
    taskkill /pid %%a /f >nul 2>&1
)

REM 启动服务
set PYTHONIOENCODING=utf-8
start /B "" cmd /c "python server_web.py > server_uvicorn.log 2>&1"
echo [%date% %time%] 服务进程已启动 >> start_log.txt

REM 等待启动
timeout /t 3 >nul

REM 获取本机IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do for /f "tokens=1" %%b in ("%%a") do set IP=%%b

echo [%date% %time%] 本机IP: %IP% >> start_log.txt
echo [%date% %time%] 服务已就绪，端口8888 >> start_log.txt

echo.
echo ✅ 服务已启动！
echo.
echo   管理端: http://%IP%:8888/server
echo   客户端: http://%IP%:8888/client
echo   本地:   http://localhost:8888/server
echo.
echo   启动日志: start_log.txt
echo   uvicorn日志: server_uvicorn.log
echo.
echo   按任意键打开管理端...
pause >nul

start http://localhost:8888/server
