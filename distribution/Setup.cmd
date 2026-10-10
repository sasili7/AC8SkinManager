@echo off

powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Setup.ps1" %*

set "AC8_SETUP_EXIT=%errorlevel%"

if not "%AC8_SETUP_EXIT%"=="0" echo Installation stopped. Read the error above.

pause

exit /b %AC8_SETUP_EXIT%

