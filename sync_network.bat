@echo off
chcp 65001 >nul
echo 🔄 同步到网络路径...
copy /Y "C:\Users\U0063\Desktop\抢答软件\server.py" "\\10.6.6.169\it_unisemiconductor.com\Tomlou\抢答软件\server.py" >nul
copy /Y "C:\Users\U0063\Desktop\抢答软件\client.py" "\\10.6.6.169\it_unisemiconductor.com\Tomlou\抢答软件\client.py" >nul
copy /Y "C:\Users\U0063\Desktop\抢答软件\README.md" "\\10.6.6.169\it_unisemiconductor.com\Tomlou\抢答软件\README.md" >nul
if exist "C:\Users\U0063\Desktop\抢答软件\question_banks.json" (
    copy /Y "C:\Users\U0063\Desktop\抢答软件\question_banks.json" "\\10.6.6.169\it_unisemiconductor.com\Tomlou\抢答软件\question_banks.json" >nul
)
echo ✅ 同步完成！
