@echo off
setlocal
cd /d "%~dp0"

REM Uma-IT launcher.
REM
REM The one thing this has to get right is the interpreter. The bot's packages
REM - cv2, paddleocr, uiautomator2 - live in system Python 3.10's
REM site-packages, not in a venv, so plain `python` picks up whatever is first
REM on PATH (3.14 on the machine this was written for) and fails at `import
REM cv2` with a message that says nothing about the real cause.
REM
REM Deliberately does NOT run `git pull`. The parent project's launcher does,
REM with `-X ours`, so starting the bot could quietly rewrite the working tree.

where py >nul 2>nul
if errorlevel 1 goto no_py

py -3.10 --version >nul 2>nul
if errorlevel 1 goto no_310

echo Starting Uma-IT...
py -3.10 main.py
goto done

:no_py
echo.
echo   The Python launcher 'py' was not found.
echo   Install Python 3.10 from python.org with the launcher option ticked.
echo.
pause
exit /b 1

:no_310
echo.
echo   Python 3.10 was not found. Installed versions:
py --list
echo.
echo   Uma-IT needs 3.10 specifically - its packages are installed there.
echo.
pause
exit /b 1

:done
REM Keep the window open if it exited badly, so the error stays readable.
if errorlevel 1 (
    echo.
    echo   Uma-IT exited with an error.
    pause
)
endlocal
