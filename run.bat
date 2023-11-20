@echo off
echo Pasting is disabled. Right-click to paste.
doskey /reinstall

mode con: cols=80 lines=25

REM 保存当前的注册表设置
REM reg query "HKCU\Console" /v QuickEdit > temp_quickedit_setting.txt
REM reg query "HKCU\Console" /v InsertMode > temp_insertmode_setting.txt

REM 禁用快速编辑模式和插入模式
REM reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f
REM reg add "HKCU\Console" /v InsertMode /t REG_DWORD /d 0 /f


%CD%/venv/scripts/python.exe %CD%/app.py