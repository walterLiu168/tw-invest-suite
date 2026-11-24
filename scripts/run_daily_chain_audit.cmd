@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python.exe"
set "LOG_DIR=%SCRIPT_DIR%_debug\daily_chain_audit"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%I"
set "LOG=%LOG_DIR%\audit_%TODAY%.log"
"%PYTHON%" "%SCRIPT_DIR%daily_chain_audit.py" --config "%SCRIPT_DIR%daily_chain_audit_config.json" --no-notify >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo daily_chain_audit exit=%RC%>> "%LOG%"
exit /b %RC%
