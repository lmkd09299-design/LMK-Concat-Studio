@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo LMK Concat Studio - publish SOURCE to your own GitHub repository.
echo No Rust/CMake/Visual Studio will be compiled on this PC.
echo GitHub Actions may consume your plan's build minutes.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\publish.ps1"
if errorlevel 1 (
 echo.
 echo Publish NOT completed. Read error above; no local video/source deleted.
 pause
 exit /b 1
)
echo.
echo Repository uploaded. Open its GitHub Actions tab to watch the Windows build.
pause
