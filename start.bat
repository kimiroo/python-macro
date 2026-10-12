@echo off
setlocal
cd /d "%~dp0"

rem Do not let the Python install manager ask questions while we are only probing for Python.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"

rem ---- 1. find Python (install it with "py install" if missing) ----
call :findpy
if not defined PY (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python was not found, and the "py" install manager is not available either.
        echo Install the Python install manager from https://www.python.org/downloads/ and run start.bat again.
        pause
        exit /b 1
    )
    echo Python was not found. Installing Python 3.13 with "py install"...
    py install -y 3.13
    call :findpy
    if not defined PY (
        echo "py install" finished but no usable Python was found.
        echo Close this window and run start.bat again, or install Python manually.
        pause
        exit /b 1
    )
)
echo Using Python: %PY%

rem ---- 2. create the virtual environment (recreate it if its Python is gone) ----
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo The existing .venv is broken. Recreating it...
        rmdir /s /q ".venv"
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
    del /q ".venv\requirements.stamp" >nul 2>nul
)

rem ---- 3. install dependencies (only for a new .venv or when requirements.txt changed) ----
fc /b requirements.txt ".venv\requirements.stamp" >nul 2>nul
if errorlevel 1 (
    echo Installing requirements...
    ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo Failed to install the requirements.
        pause
        exit /b 1
    )
    copy /y requirements.txt ".venv\requirements.stamp" >nul
)

rem ---- 4. run ----
".venv\Scripts\python.exe" main.py
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo The macro exited with an error.
    echo.
)
echo Press any keys to exit...
pause > nul
exit /b %RC%

rem ---- helper: sets PY to a working Python command, or leaves it empty ----
:findpy
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if defined PY goto :eof
python -c "import sys" >nul 2>nul && set "PY=python"
if defined PY goto :eof
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY="%LocalAppData%\Programs\Python\Python313\python.exe""
goto :eof
