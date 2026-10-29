@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "LMK-Concat-Studio.exe" (
  echo ERROR: LMK-Concat-Studio.exe is not present. This is not a complete release.
  pause
  exit /b 1
)
if not exist "runtime\cli.py" (
  echo ERROR: runtime\cli.py missing. This is not a complete release.
  pause
  exit /b 1
)
if not exist "runtime\.venv\Scripts\python.exe" (
  echo First launch: preparing local LMK video tools...
  py -3.12 -m venv "runtime\.venv" || (
    echo Python 3.12 is needed for LMK video tools. Install from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  "runtime\.venv\Scripts\python.exe" -m pip install -r "runtime\requirements.txt" || (
    echo Failed to install speech dependencies. Inspect the output above.
    pause
    exit /b 1
  )
)
set "PATH=%CD%;%PATH%"
set "LMK_TOOLS_HOME=%CD%\runtime"
set "LMK_PYTHON=%CD%\runtime\.venv\Scripts\python.exe"
start "LMK Concat Studio" "%CD%\LMK-Concat-Studio.exe"
